"""
Etapa 2 — corte dos documentos em trechos.

Lê os `.txt` do corpus e produz `data/chunks.jsonl`, uma linha por chunk, com
os metadados de proveniência que permitem citar a fonte lá na geração.

A estratégia de corte é plugável (`ESTRATEGIAS`). A padrão continua sendo o
corte por parágrafo, e a saída é byte a byte idêntica à da versão anterior do
projeto — trocar o corte invalidaria o índice já construído, que custa horas
de processamento para refazer. O corte sensível à estrutura por seção descrito
em `docs/fase-1-corpus.md` entra aqui como mais uma estratégia, quando for a
hora, sem mexer no resto.
"""

import json
import os
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

from ..config import ConfigChunking
from ..erros import ErroPreRequisito
from ..modelos import Chunk, ResultadoEtapa
from . import RelatorProgresso, sem_progresso


@dataclass
class ResultadoCorte:
    """Trechos de um documento, mais o aviso de que houve parágrafo fora do teto."""

    textos: list[str]
    teve_paragrafo_gigante: bool = False


# ── divisão de parágrafo acima do teto ────────────────────────────────────


def _agrupar_respeitando_teto(itens: list[str], tamanho_maximo: int, separador: str) -> list[str]:
    """Junta itens (frases ou palavras) em pedaços sem ultrapassar o teto."""
    pedacos: list[str] = []
    atual = ""

    for item in itens:
        candidato = f"{atual}{separador}{item}" if atual else item
        if atual and len(candidato) > tamanho_maximo:
            pedacos.append(atual)
            atual = item
        else:
            atual = candidato

    if atual:
        pedacos.append(atual)

    return pedacos


def dividir_paragrafo_gigante(texto: str, tamanho_maximo: int) -> list[str]:
    """Subdivide um 'parágrafo' acima do teto — quase sempre página de lista.

    Três planos, em ordem de preferência: corta por frase (preserva sentido);
    se não houver pontuação que guie o corte, por palavra; e se nem espaço
    houver (token único gigantesco), corte bruto por caractere. O plano C é o
    que torna o teto uma garantia de verdade, e não uma tendência.
    """
    pedacos_por_frase = _agrupar_respeitando_teto(re.split(r"(?<=[.!?])\s+", texto), tamanho_maximo, separador=" ")

    resultado: list[str] = []
    for pedaco in pedacos_por_frase:
        if len(pedaco) <= tamanho_maximo:
            resultado.append(pedaco)
            continue

        for sub in _agrupar_respeitando_teto(pedaco.split(" "), tamanho_maximo, separador=" "):
            if len(sub) <= tamanho_maximo:
                resultado.append(sub)
            else:
                for i in range(0, len(sub), tamanho_maximo):
                    resultado.append(sub[i : i + tamanho_maximo])

    return [p.strip() for p in resultado if p.strip()]


# ── estratégias de corte ──────────────────────────────────────────────────


def cortar_por_paragrafo(corpo: str, config: ConfigChunking) -> ResultadoCorte:
    """Corte padrão: um chunk por parágrafo (bloco separado por linha em branco).

    Parágrafos abaixo do mínimo são descartados — linha solta, título de seção
    sem corpo, legenda de imagem: nada que se sustente como resposta sozinho.
    """
    textos: list[str] = []
    teve_gigante = False

    for paragrafo in re.split(r"\n\s*\n", corpo):
        texto_limpo = paragrafo.strip()
        if len(texto_limpo) < config.tamanho_minimo:
            continue

        if len(texto_limpo) > config.tamanho_maximo:
            teve_gigante = True
            pedacos = dividir_paragrafo_gigante(texto_limpo, config.tamanho_maximo)
        else:
            pedacos = [texto_limpo]

        textos.extend(p for p in pedacos if len(p) >= config.tamanho_minimo)

    return ResultadoCorte(textos, teve_gigante)


def cortar_por_paragrafo_agrupado(corpo: str, config: ConfigChunking) -> ResultadoCorte:
    """Variante: junta parágrafos curtos consecutivos até se aproximarem do teto.

    Existe porque a estratégia padrão joga fora todo parágrafo com menos de
    `tamanho_minimo` caracteres — em artigos de diálogo ou lista de citações,
    isso descarta conteúdo real. Aqui esses parágrafos são agrupados em vez de
    perdidos.

    Não é a padrão: mudar a saída obriga a reindexar o corpus inteiro. Fica
    disponível para quando a próxima indexação for acontecer de qualquer jeito.
    """
    paragrafos = [p.strip() for p in re.split(r"\n\s*\n", corpo) if p.strip()]
    teve_gigante = False
    textos: list[str] = []
    acumulado = ""

    for paragrafo in paragrafos:
        if len(paragrafo) > config.tamanho_maximo:
            if acumulado:
                textos.append(acumulado)
                acumulado = ""
            teve_gigante = True
            textos.extend(dividir_paragrafo_gigante(paragrafo, config.tamanho_maximo))
            continue

        candidato = f"{acumulado}\n\n{paragrafo}" if acumulado else paragrafo
        if len(candidato) > config.tamanho_maximo:
            textos.append(acumulado)
            acumulado = paragrafo
        else:
            acumulado = candidato

    if acumulado:
        textos.append(acumulado)

    return ResultadoCorte([t for t in textos if len(t) >= config.tamanho_minimo], teve_gigante)


ESTRATEGIAS: dict[str, Callable[[str, ConfigChunking], ResultadoCorte]] = {
    "paragrafo": cortar_por_paragrafo,
    "paragrafo_agrupado": cortar_por_paragrafo_agrupado,
}


# ── leitura do corpus ─────────────────────────────────────────────────────


def extrair_titulo_e_corpo(conteudo: str) -> tuple[str, str]:
    """Separa o cabeçalho '# Título' do corpo, no formato que o download grava."""
    linhas = conteudo.split("\n", 2)
    titulo = linhas[0].lstrip("#").strip() if linhas and linhas[0].startswith("#") else "desconhecido"
    corpo = linhas[2] if len(linhas) > 2 else ""
    return titulo, corpo


def gerar_chunks_do_documento(caminho: Path, config: ConfigChunking) -> tuple[list[Chunk], bool]:
    """Chunks de um documento. Unidade testável, sem I/O de saída."""
    nome_arquivo = caminho.name
    conteudo = caminho.read_text(encoding="utf-8")
    titulo, corpo = extrair_titulo_e_corpo(conteudo)

    corte = ESTRATEGIAS[config.estrategia](corpo, config)

    chunks = [
        Chunk(
            chunk_id=f"{nome_arquivo}::{indice}",
            texto=texto,
            documento_origem=nome_arquivo,
            titulo_pagina=titulo,
            chunk_index=indice,
        )
        for indice, texto in enumerate(corte.textos)
    ]
    return chunks, corte.teve_paragrafo_gigante


def percorrer_corpus(pasta: Path, config: ConfigChunking) -> Iterator[tuple[list[Chunk], str, bool]]:
    """Gera os chunks documento a documento, sem carregar o corpus na memória."""
    for caminho in sorted(pasta.glob("*.txt")):
        chunks, teve_gigante = gerar_chunks_do_documento(caminho, config)
        yield chunks, caminho.name, teve_gigante


# ── etapa ─────────────────────────────────────────────────────────────────


def executar(
    config: ConfigChunking,
    pasta_corpus: Path,
    arquivo_saida: Path,
    progresso: RelatorProgresso = sem_progresso,
) -> ResultadoEtapa:
    """Corta o corpus inteiro e grava o JSONL.

    A escrita é feita num arquivo temporário e movida por cima do destino no
    final: uma interrupção no meio deixa o `chunks.jsonl` anterior intacto, em
    vez de um arquivo truncado que a indexação leria como se estivesse completo.
    """
    if config.estrategia not in ESTRATEGIAS:
        raise ErroPreRequisito(
            f"Estratégia de chunking desconhecida: '{config.estrategia}'.",
            sugestao=f"Disponíveis: {', '.join(ESTRATEGIAS)}.",
        )

    arquivos = sorted(pasta_corpus.glob("*.txt"))
    if not arquivos:
        raise ErroPreRequisito(
            f"Nenhum arquivo .txt em {pasta_corpus}.",
            sugestao="Rode a etapa de download do corpus antes desta.",
        )

    resultado = ResultadoEtapa()
    documentos_com_gigante: list[str] = []
    total_caracteres = 0
    menor = maior = 0
    documentos_vistos = 0

    arquivo_saida.parent.mkdir(parents=True, exist_ok=True)
    temporario = arquivo_saida.with_suffix(arquivo_saida.suffix + ".parcial")

    try:
        with temporario.open("w", encoding="utf-8") as saida:
            for indice, (chunks, nome, teve_gigante) in enumerate(percorrer_corpus(pasta_corpus, config), start=1):
                documentos_vistos += 1
                if teve_gigante:
                    documentos_com_gigante.append(nome)

                for chunk in chunks:
                    saida.write(json.dumps(chunk.como_dicionario(), ensure_ascii=False) + "\n")
                    tamanho = len(chunk.texto)
                    total_caracteres += tamanho
                    menor = tamanho if menor == 0 else min(menor, tamanho)
                    maior = max(maior, tamanho)
                    resultado.processados += 1

                if indice % 200 == 0 or indice == len(arquivos):
                    progresso(indice, len(arquivos), f"{resultado.processados} chunks")

        os.replace(temporario, arquivo_saida)
    finally:
        temporario.unlink(missing_ok=True)

    resultado.detalhes = {
        "documentos": documentos_vistos,
        "documentos_com_paragrafo_gigante": documentos_com_gigante,
        "tamanho_minimo": menor,
        "tamanho_medio": total_caracteres // resultado.processados if resultado.processados else 0,
        "tamanho_maximo": maior,
        "arquivo": arquivo_saida,
    }
    return resultado
