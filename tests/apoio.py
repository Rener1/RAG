"""
Apoio comum aos testes: caminho de import e dublês das dependências externas.

Os dublês existem para que os testes rodem sem Qdrant, sem Ollama e sem rede —
o que é o ponto da modularidade: as etapas dependem dos protocolos, então uma
implementação de mentira serve tão bem quanto a real.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rag.modelos import Chunk, TrechoRecuperado  # noqa: E402


class EmbutidorFalso:
    """Vetores determinísticos, sem chamar o Ollama."""

    def __init__(self, dimensao: int = 4) -> None:
        self._dimensao = dimensao
        self.chamadas: list[list[str]] = []

    @property
    def dimensao(self) -> int:
        return self._dimensao

    def embutir(self, textos: list[str]) -> list[list[float]]:
        self.chamadas.append(list(textos))
        return [[float(len(t) % 7), 1.0, 0.0, 0.5] for t in textos]


class RepositorioFalso:
    """Banco vetorial em memória, com a mesma forma do RepositorioQdrant."""

    def __init__(self, dimensao_existente: int | None = None) -> None:
        self.pontos: dict[str, Chunk] = {}
        self.dimensao_existente = dimensao_existente
        self.recriado = False
        self.colecao = "teste"

    def garantir_colecao(self, dimensao: int, recriar: bool = False) -> None:
        if recriar:
            self.pontos.clear()
            self.recriado = True
        self.dimensao_existente = dimensao

    def contar_pontos(self) -> int:
        return len(self.pontos)

    def dimensao_da_colecao(self) -> int | None:
        return self.dimensao_existente

    def ids_existentes(self, chunk_ids: list[str]) -> set[str]:
        return {c for c in chunk_ids if c in self.pontos}

    def inserir(self, chunks: list[Chunk], vetores: list[list[float]]) -> int:
        for chunk, _ in zip(chunks, vetores, strict=True):
            self.pontos[chunk.chunk_id] = chunk
        return len(chunks)

    def buscar(self, vetor: list[float], k: int, score_minimo: float = 0.0) -> list[TrechoRecuperado]:
        return [
            TrechoRecuperado(
                texto=chunk.texto,
                titulo_pagina=chunk.titulo_pagina,
                documento_origem=chunk.documento_origem,
                chunk_id=chunk.chunk_id,
                score=0.9,
            )
            for chunk in list(self.pontos.values())[:k]
        ]


class GeradorFalso:
    """Devolve o prompt recebido em pedaços — permite inspecionar o que foi montado."""

    def __init__(self) -> None:
        self.ultimo_prompt = ""

    def gerar(self, prompt: str):
        self.ultimo_prompt = prompt
        yield "resposta "
        yield "gerada"


class ColetorFalso:
    """Wiki de mentira, para testar a etapa de download sem tocar na rede."""

    def __init__(self, paginas: dict[str, str]) -> None:
        self.paginas = paginas
        self.lotes_pedidos: list[list[str]] = []

    def descobrir_namespace(self) -> int:
        return 130

    def listar_titulos(self, namespace_id: int, limite: int) -> list[str]:
        return list(self.paginas)[:limite]

    def baixar_lote(self, titulos: list[str]) -> dict[str, str]:
        self.lotes_pedidos.append(list(titulos))
        return {t: self.paginas[t] for t in titulos if t in self.paginas}
