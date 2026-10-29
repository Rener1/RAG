"""
As etapas do pipeline, uma por módulo.

A ordem importa — cada etapa consome o artefato da anterior:

    download → chunking → indexacao → recuperacao → geracao

`extracao` é a porta de entrada do acervo real: tira o texto dos PDFs da
exportação do DSpace (`data/texto_acervo/`). Por enquanto nada a consome — o
chunking ainda lê o corpus de teste.

Nenhum módulo daqui importa outro. A comunicação é por artefato em disco
(`data/corpus_uesp/`, `data/chunks.jsonl`, coleção no banco vetorial), o que
permite refazer uma etapa sozinha sem tocar nas demais.
"""

from collections.abc import Callable

# (feito, total, rótulo) — as etapas relatam progresso por aqui em vez de
# imprimir direto, para não amarrar o pipeline a um formato de saída.
RelatorProgresso = Callable[[int, int, str], None]


def sem_progresso(feito: int, total: int, rotulo: str) -> None:
    """Relator nulo — o padrão quando ninguém está olhando (testes, scripts)."""
