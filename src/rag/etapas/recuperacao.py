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
        """Trechos mais próximos da pergunta, do mais para o menos similar."""
        # NOTE: ponto de entrada do intermediador de decomposição de consulta,
        # combinado para depois e ainda não implementado — pergunta composta
        # vira N sub-perguntas, cada uma buscada em separado, e os resultados
        # se combinam antes de montar o prompt. Fica aqui, e não na geração,
        # porque é decisão de recuperação.
        vetor = self._embutidor.embutir([pergunta])[0]
        return self._repositorio.buscar(
            vetor,
            k=k or self._config.k,
            score_minimo=self._config.score_minimo,
        )
