#!/usr/bin/env python3
"""
Ponto de entrada único do pipeline RAG da IA Freiriana.

Tudo passa por aqui: diagnóstico, download do corpus, chunking, indexação,
busca e perguntas. Sem argumento, abre o menu interativo.

    python3 main.py                       menu interativo
    python3 main.py --help                todos os subcomandos
    python3 main.py perguntar "..."       ciclo RAG completo

Este arquivo é deliberadamente fino: ele só coloca `src/` no caminho de import
e delega. A lógica está no pacote `rag`.
"""

import sys
from pathlib import Path

# O projeto não é instalado com pip (roda sem virtualenv, direto do clone),
# então `src/` entra no caminho de import aqui. É a única linha de mágica do
# projeto — em troca, `python3 main.py` funciona num clone recém-baixado, sem
# `pip install -e .` nem PYTHONPATH.
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from rag.interface.cli import principal  # noqa: E402  (precisa vir depois do sys.path)

if __name__ == "__main__":
    raise SystemExit(principal())
