"""
Etapa 4 — recuperação.

Pergunta em português → vetor → trechos mais próximos no banco vetorial.
Nenhum LLM de geração envolvido: esta etapa é isolável de propósito, porque
recall@k é avaliável sem gerar uma linha de texto (`docs/fase-3-avaliacao-e-servidor.md`).

Ao depurar qualidade de resposta, o lugar de olhar primeiro é aqui: se o
trecho certo não foi recuperado, nenhum ajuste de prompt conserta a resposta.
"""

from ..config import ConfigBusca
from ..modelos import TrechoRecuperado
from ..protocolos import Embutidor, RepositorioVetorial


class Recuperador:
    """Recuperação de trechos. Depende dos protocolos, não das implementações."""

    def __init__(self, embutidor: Embutidor, repositorio: RepositorioVetorial, config: ConfigBusca) -> None:
        self._embutidor = embutidor
        self._repositorio = repositorio
        self._config = config

    def buscar(self, pergunta: str, k: int | None = None) -> list[TrechoRecuperado]:
        """Trechos mais próximos da pergunta, do mais para o menos similar.

        Busca direta, uma consulta e um vetor. A decomposição de pergunta
        composta em N sub-consultas vive em `rag.mediacao`, envolvendo esta
        classe por injeção — não aqui dentro. É o que mantém esta etapa como a
        linha de base contra a qual a mediação é comparável
        (`buscar --sem-intermediar`).
        """
        vetor = self._embutidor.embutir([pergunta])[0]
        return self._repositorio.buscar(
            vetor,
            k=k or self._config.k,
            score_minimo=self._config.score_minimo,
        )
