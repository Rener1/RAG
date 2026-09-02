"""
Orquestração do ciclo RAG: pergunta → recuperação → prompt aumentado → geração.

Mora fora de `etapas/` de propósito. As etapas não importam umas às outras —
é o que permite refazer uma sem mexer nas demais — e amarrar recuperação com
geração é justamente o trabalho de composição que não pertence a nenhuma das
duas.
"""

import time
from collections.abc import Callable, Iterator

from .etapas.geracao import caber_no_orcamento, estimar_tokens, montar_prompt
from .modelos import Resposta, TrechoRecuperado
from .protocolos import Gerador, RecuperadorDeTrechos


class MotorRag:
    """Ciclo completo: pergunta → recuperação → prompt aumentado → geração.

    Recebe recuperador e gerador prontos em vez de construí-los: é o que
    permite testar a geração com um recuperador falso, e trocar o modelo sem
    tocar nesta classe. O montador de prompt também é injetável — é por ali
    que o marco pedagógico entra, sem alterar esta classe.
    """

    def __init__(
        self,
        recuperador: RecuperadorDeTrechos,
        gerador: Gerador,
        montador_de_prompt: Callable[[str, list[TrechoRecuperado]], str] = montar_prompt,
        orcamento_em_tokens: int = 0,
        ao_ajustar_contexto: Callable[[int, int], None] = lambda recuperados, usados: None,
    ) -> None:
        self._recuperador = recuperador
        self._gerador = gerador
        self._montar_prompt = montador_de_prompt
        self._orcamento = orcamento_em_tokens
        self._ao_ajustar_contexto = ao_ajustar_contexto

    def _ajustar_ao_orcamento(self, pergunta: str, trechos: list[TrechoRecuperado]) -> list[TrechoRecuperado]:
        """Descarta os trechos que não cabem na janela do modelo.

        O overhead — marco, pergunta, andaime do prompt — é medido chamando o
        próprio montador com zero trechos. Assim a conta funciona igual com e sem
        marco, e um marco longo escrito pelo comitê encolhe o espaço de trechos
        sozinho, sem ninguém precisar lembrar de reajustar `k`.

        Fica aqui, e não no montador, para que a lista devolvida à interface seja
        a mesma que foi ao modelo: exibir doze fontes e mandar sete ao prompt
        faria `validar_citacoes` aprovar uma fonte que o modelo nunca viu.
        """
        if self._orcamento <= 0:
            return trechos

        overhead = estimar_tokens(self._montar_prompt(pergunta, []))
        cabem = caber_no_orcamento(trechos, self._orcamento, overhead)
        if len(cabem) < len(trechos):
            self._ao_ajustar_contexto(len(trechos), len(cabem))
        return cabem

    def recuperar(self, pergunta: str, k: int | None = None) -> list[TrechoRecuperado]:
        return self._recuperador.buscar(pergunta, k=k)

    def responder_em_fluxo(
        self,
        pergunta: str,
        k: int | None = None,
    ) -> tuple[list[TrechoRecuperado], Iterator[str]]:
        """Devolve os trechos na hora e a resposta como fluxo de pedaços.

        Separado assim para a interface poder mostrar as fontes recuperadas
        antes de o modelo começar a escrever — quem pergunta vê em cima de que
        material a resposta está sendo construída, em vez de esperar em branco.
        """
        trechos = self.recuperar(pergunta, k=k)
        if not trechos:
            return [], iter(())
        trechos = self._ajustar_ao_orcamento(pergunta, trechos)
        return trechos, self._gerador.gerar(self._montar_prompt(pergunta, trechos))

    def responder(self, pergunta: str, k: int | None = None) -> Resposta:
        """Versão de uma tacada só — usada por script e teste, não pela interface."""
        inicio = time.monotonic()
        trechos, fluxo = self.responder_em_fluxo(pergunta, k=k)
        texto = "".join(fluxo)
        return Resposta(
            pergunta=pergunta,
            texto=texto,
            trechos=trechos,
            segundos=time.monotonic() - inicio,
        )
