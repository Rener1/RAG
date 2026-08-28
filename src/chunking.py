"""
Chunking do corpus — lê os .txt baixados em data/corpus_uesp/, corta em trechos e anexa
metadados de proveniência. Não toca em embedding, Qdrant ou LLM: essa
etapa produz só o material bruto que a próxima etapa (embedding) vai
consumir. É a etapa "seu script" do diagrama que já vimos — cinza, não roxa.

Corte por parágrafo (linha em branco separando blocos), a mesma estratégia
do protótipo original. Ainda não é o corte sensível à estrutura por seção
que o fase-1-corpus.md descreve — isso fica pra depois de vermos como a
recuperação se comporta com o corte simples primeiro.

Saída: um arquivo JSONL (uma linha = um chunk), pronto pra próxima etapa ler.

Rode:  python3 src/chunking.py
"""

import glob
import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parents[1]  # paths independem de onde o script é chamado

PASTA_CORPUS = RAIZ_PROJETO / "data" / "corpus_uesp"
ARQUIVO_SAIDA = RAIZ_PROJETO / "data" / "chunks.jsonl"
TAMANHO_MINIMO_CHUNK = 60  # caracteres — abaixo disso, o trecho não carrega informação útil sozinho
TAMANHO_MAXIMO_CHUNK = 2000  # caracteres — acima disso, o "parágrafo" provavelmente é uma página de
# lista/índice sem quebra de linha real; precisa ser subdividido


@dataclass
class Chunk:
    chunk_id: str  # documento::índice — identificador único e legível
    texto: str
    documento_origem: str  # nome do arquivo — proveniência
    titulo_pagina: str  # título do artigo da wiki (equivalente a "página" pra esse corpus)
    chunk_index: int  # posição do chunk dentro do documento


def extrair_titulo_e_corpo(conteudo: str) -> tuple[str, str]:
    """Os arquivos salvos pelo script de download começam com '# Título',
    seguido de uma linha em branco e o corpo do artigo."""
    linhas = conteudo.split("\n", 2)
    titulo = linhas[0].lstrip("#").strip() if linhas and linhas[0].startswith("#") else "desconhecido"
    corpo = linhas[2] if len(linhas) > 2 else ""
    return titulo, corpo


def _agrupar_respeitando_teto(itens: list[str], tamanho_maximo: int, separador: str) -> list[str]:
    """Agrupa itens (frases ou palavras) em pedaços, sem ultrapassar o teto."""
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
    """Um 'parágrafo' acima do teto normalmente é uma página de lista/índice
    sem quebra de linha real. Tenta cortar por frase primeiro (preserva o
    sentido); se o texto não tem pontuação pra guiar isso (lista sem ponto
    final, por exemplo), cai pra corte por palavra; se nem isso houver
    (bloco sem espaço nenhum — caso patológico), corta bruto por caractere.
    Isso garante um teto de verdade, não só "na maioria dos casos"."""

    pedacos_por_frase = _agrupar_respeitando_teto(re.split(r"(?<=[.!?])\s+", texto), tamanho_maximo, separador=" ")

    resultado: list[str] = []
    for pedaco in pedacos_por_frase:
        if len(pedaco) <= tamanho_maximo:
            resultado.append(pedaco)
            continue

        # plano B: sem pontuação suficiente — corta por palavra
        pedacos_por_palavra = _agrupar_respeitando_teto(pedaco.split(" "), tamanho_maximo, separador=" ")
        for sub in pedacos_por_palavra:
            if len(sub) <= tamanho_maximo:
                resultado.append(sub)
            else:
                # plano C: nem espaço tem (token único gigantesco) — corte bruto por caractere
                for i in range(0, len(sub), tamanho_maximo):
                    resultado.append(sub[i : i + tamanho_maximo])

    return [p.strip() for p in resultado if p.strip()]


def fatiar_em_chunks(pasta: str) -> tuple[list[Chunk], list[str]]:
    chunks: list[Chunk] = []
    documentos_com_paragrafo_gigante: list[str] = []
    arquivos = sorted(glob.glob(f"{pasta}/*.txt"))

    for caminho in arquivos:
        nome_arquivo = os.path.basename(caminho)
        conteudo = open(caminho, encoding="utf-8").read()
        titulo, corpo = extrair_titulo_e_corpo(conteudo)

        paragrafos = re.split(r"\n\s*\n", corpo)
        indice_valido = 0

        for paragrafo in paragrafos:
            texto_limpo = paragrafo.strip()
            if len(texto_limpo) < TAMANHO_MINIMO_CHUNK:
                continue  # descarta linha solta, título de seção sem corpo, etc.

            if len(texto_limpo) > TAMANHO_MAXIMO_CHUNK:
                if nome_arquivo not in documentos_com_paragrafo_gigante:
                    documentos_com_paragrafo_gigante.append(nome_arquivo)
                sub_pedacos = dividir_paragrafo_gigante(texto_limpo, TAMANHO_MAXIMO_CHUNK)
            else:
                sub_pedacos = [texto_limpo]

            for pedaco in sub_pedacos:
                if len(pedaco) < TAMANHO_MINIMO_CHUNK:
                    continue
                chunks.append(
                    Chunk(
                        chunk_id=f"{nome_arquivo}::{indice_valido}",
                        texto=pedaco,
                        documento_origem=nome_arquivo,
                        titulo_pagina=titulo,
                        chunk_index=indice_valido,
                    )
                )
                indice_valido += 1

    return chunks, documentos_com_paragrafo_gigante


def salvar_jsonl(chunks: list[Chunk], caminho_saida: str) -> None:
    with open(caminho_saida, "w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(asdict(chunk), ensure_ascii=False) + "\n")


def imprimir_estatisticas(chunks: list[Chunk]) -> None:
    if not chunks:
        print("Nenhum chunk gerado — confira se data/corpus_uesp/ tem arquivos .txt.")
        return

    tamanhos = [len(c.texto) for c in chunks]
    documentos = {c.documento_origem for c in chunks}

    print(f"Documentos processados: {len(documentos)}")
    print(f"Chunks gerados: {len(chunks)}")
    print(f"Média de chunks por documento: {len(chunks) / len(documentos):.1f}")
    print(
        f"Tamanho do chunk — mín: {min(tamanhos)}, média: {sum(tamanhos) // len(tamanhos)}, máx: {max(tamanhos)} caracteres"
    )


if __name__ == "__main__":
    chunks, documentos_com_paragrafo_gigante = fatiar_em_chunks(PASTA_CORPUS)
    imprimir_estatisticas(chunks)

    if documentos_com_paragrafo_gigante:
        print(
            f"\n{len(documentos_com_paragrafo_gigante)} documento(s) tinham parágrafo acima de "
            f"{TAMANHO_MAXIMO_CHUNK} caracteres (provavelmente páginas de lista/índice) — "
            f"foram subdivididos por frase automaticamente:"
        )
        for nome in documentos_com_paragrafo_gigante[:20]:
            print(f"  - {nome}")
        if len(documentos_com_paragrafo_gigante) > 20:
            print(f"  ... e mais {len(documentos_com_paragrafo_gigante) - 20}")

    salvar_jsonl(chunks, ARQUIVO_SAIDA)
    print(f"\nSalvo em {ARQUIVO_SAIDA} — pronto pra etapa de embedding.")
