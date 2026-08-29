"""
Etapa 1 — coleta do corpus de teste.

Orquestra o download: pede a lista de títulos ao coletor, distribui em lotes
paralelos, limpa o wikitext e grava um `.txt` por página em
`data/corpus_uesp/`. Quem fala com a rede é o coletor injetado
(`rag.clientes.uesp.ColetorUESP`), não este módulo.

O corpus é descartável: existe para exercitar o pipeline com volume real
enquanto o acervo do Centro de Referência Paulo Freire não fica pronto. Trocar
para o corpus real é escrever outro coletor — esta etapa continua igual.
"""

import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import mwparserfromhell

from ..config import ConfigDownload
from ..modelos import ResultadoEtapa
from ..protocolos import ColetorDeCorpus
from . import RelatorProgresso, sem_progresso

# <ref>...</ref> sai antes da limpeza geral: senão o texto da citação entra
# misturado no meio do parágrafo e vira ruído dentro do chunk.
PADRAO_REFERENCIAS = re.compile(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>", re.DOTALL | re.IGNORECASE)
PADRAO_CARACTERE_INVALIDO = re.compile(r"[^\w\-]+")


def nome_arquivo_seguro(titulo: str) -> str:
    """Título da wiki → nome de arquivo.

    Títulos distintos podem colidir aqui ("A B" e "A-B" viram "A_B"). Mantido
    assim de propósito: o nome do arquivo compõe o `chunk_id`, que é a chave
    do índice — mudar o esquema invalidaria o corpus indexado inteiro, por um
    punhado de páginas num corpus que é descartável.
    """
    return PADRAO_CARACTERE_INVALIDO.sub("_", titulo).strip("_") + ".txt"


def limpar_wikitexto(wikitexto: str) -> str:
    """Wikitext → texto corrido. Devolve vazio para redirect (não tem conteúdo próprio)."""
    if wikitexto.strip().upper().startswith("#REDIRECT"):
        return ""
    sem_referencias = PADRAO_REFERENCIAS.sub("", wikitexto)
    return mwparserfromhell.parse(sem_referencias).strip_code().strip()


def executar(
    config: ConfigDownload,
    pasta_saida: Path,
    coletor: ColetorDeCorpus,
    progresso: RelatorProgresso = sem_progresso,
) -> ResultadoEtapa:
    """Baixa o namespace inteiro. Seguro de repetir: pula o que já está em disco.

    O coletor entra por injeção — é o que permite testar esta função inteira
    sem tocar na rede.
    """
    pasta_saida.mkdir(parents=True, exist_ok=True)

    namespace_id = coletor.descobrir_namespace()
    titulos = coletor.listar_titulos(namespace_id, config.candidatos)

    lotes = [titulos[i : i + config.titulos_por_lote] for i in range(0, len(titulos), config.titulos_por_lote)]
    resultado = ResultadoEtapa()
    resultado.detalhes = {"titulos_encontrados": len(titulos), "lotes": len(lotes), "pasta": pasta_saida}

    trava = threading.Lock()
    processados = 0

    def processar(lote: list[str]) -> tuple[int, int]:
        """Roda numa thread: baixa, limpa e grava um lote inteiro."""
        # Filtrar antes da requisição é o que torna a repetição barata: um
        # download interrompido retoma sem rebaixar o que já está em disco.
        pendentes = [t for t in lote if not (pasta_saida / nome_arquivo_seguro(t)).exists()]
        if not pendentes:
            return 0, 0

        salvos = descartados = 0
        for titulo, wikitexto in coletor.baixar_lote(pendentes).items():
            texto = limpar_wikitexto(wikitexto)
            if len(texto) < config.tamanho_minimo:
                descartados += 1
                continue
            (pasta_saida / nome_arquivo_seguro(titulo)).write_text(f"# {titulo}\n\n{texto}", encoding="utf-8")
            salvos += 1
        return salvos, descartados

    with ThreadPoolExecutor(max_workers=config.lotes_paralelos) as executor:
        futuros = {executor.submit(processar, lote): lote for lote in lotes}

        for futuro in as_completed(futuros):
            try:
                salvos, descartados = futuro.result()
            except Exception as erro:
                resultado.falhas.append(str(erro))
                salvos = descartados = 0

            with trava:
                processados += 1
                resultado.processados += salvos
                resultado.ignorados += descartados
                progresso(processados, len(lotes), f"{resultado.processados} páginas salvas")

    return resultado
