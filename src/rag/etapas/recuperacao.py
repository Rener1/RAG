"""
Etapa 4 — recuperação.

Pergunta em português → vetor → trechos mais próximos no banco vetorial.
Nenhum LLM de geração envolvido: esta etapa é isolável de propósito, porque
recall@k é avaliável sem gerar uma linha de texto (`docs/plano/fase-3-avaliacao-e-servidor.md`).

Ao depurar qualidade de resposta, o lugar de olhar primeiro é aqui: se o
trecho certo não foi recuperado, nenhum ajuste de prompt conserta a resposta.
"""

from ..config import ConfigBusca
from ..erros import ErroPipeline
from ..modelos import TrechoRecuperado
from ..protocolos import Embutidor, Reordenador, RepositorioVetorial


def decidir_quantidade(
    candidatos: list[TrechoRecuperado],
    config: ConfigBusca,
    k: int | None,
    reordenados: bool,
) -> list[TrechoRecuperado]:
    """Quantos trechos entregar, conforme quem decidiu a ordem.

    Existe como função separada porque **dois caminhos precisam da mesma
    decisão** — a busca direta e a mediação, que funde rankings. Duplicá-la fez
    um conserto valer só num dos lados, e a mediação continuou devolvendo 18
    trechos depois de a busca direta já estar corrigida.

    **Com reordenação, quantidade fixa.** O corte relativo pergunta "o que está
    perto do melhor?" olhando o cosseno, e pressupõe a lista ordenada por ele.
    Depois de reordenar isso deixa de valer: quem ordena é o cross-encoder, por
    um critério que não é o cosseno, e o primeiro colocado pode ter similaridade
    menor que o terceiro. Medido numa pergunta real, o topo tinha 0,600 e o
    terceiro 0,665 — o corte caía de 0,598 para 0,540 e devolvia 21 trechos,
    acima do próprio teto.

    Não é caso de trocar o primeiro pelo maior: seria remendar a conta e manter
    a incoerência. Depois de reordenar, cortar por cosseno não significa nada. O
    reordenador **é** a seleção — entregar os `k` melhores dele é o desenho de
    dois estágios como ele existe.
    """
    # `k` explícito manda: quem passou um número quer aquele número, e é o que
    # mantém a varredura de `k` do harness comparável.
    if k is not None:
        return candidatos[:k]
    if reordenados or config.limiar_relativo <= 0:
        return candidatos[: config.k]
    return recortar_por_limiar_relativo(candidatos, config.limiar_relativo, config.k_minimo)


def recortar_por_limiar_relativo(
    trechos: list[TrechoRecuperado],
    limiar: float,
    minimo: int,
) -> list[TrechoRecuperado]:
    """Mantém os trechos próximos do primeiro colocado, com um piso.

    A quantidade passa a depender da pergunta: onde o score despenca depois do
    segundo trecho, voltam poucos; onde fica num platô, voltam muitos. Medido
    nos 40 casos com `limiar = 0,90`, a média foi de 7,3 trechos para dúvida
    factual, 10,7 para exploração e 12,6 para pedido de produto — a ordem que se
    esperaria, e o motivo de a política existir.

    **Relativo ao topo de cada pergunta, nunca absoluto.** O score do primeiro
    colocado varia de 0,526 a 0,724 conforme a pergunta, então um corte fixo é
    frouxo para umas e mortal para outras. Pior: as faixas de score de trecho
    relevante e irrelevante se sobrepõem quase por inteiro neste corpus, de modo
    que corte absoluto nenhum separa os dois. O relativo não tenta separar —
    ele só mede onde a lista para de ser parecida com o próprio topo.

    O piso existe porque similaridade alta e isolada não quer dizer resposta
    completa: uma pergunta cujo topo destoa dos demais devolveria um trecho só,
    e uma fonte só é pouco para fundamentar qualquer coisa.
    """
    if not trechos or limiar <= 0:
        return list(trechos)

    corte = limiar * trechos[0].score
    aceitos = [trecho for trecho in trechos if trecho.score >= corte]
    return aceitos if len(aceitos) >= minimo else trechos[:minimo]


class Recuperador:
    """Recuperação de trechos. Depende dos protocolos, não das implementações."""

    def __init__(
        self,
        embutidor: Embutidor,
        repositorio: RepositorioVetorial,
        config: ConfigBusca,
        reordenador: Reordenador | None = None,
    ) -> None:
        self._embutidor = embutidor
        self._repositorio = repositorio
        self._config = config
        self._reordenador = reordenador

    def _quantos_candidatos(self, k: int | None) -> int:
        """Quantos trechos pedir ao banco antes de recortar.

        Com reordenação, o pool é grande de propósito: um cross-encoder só
        melhora o que recebe, e receber 20 candidatos mede pior que receber 50.
        """
        if self._reordenador is not None and self._config.reordenar:
            return max(self._config.candidatos_para_reordenar, k or 0)
        if k is not None:
            return k
        if self._config.limiar_relativo > 0:
            return self._config.k_maximo
        return self._config.k

    def _reordenar(self, pergunta: str, trechos: list[TrechoRecuperado]) -> list[TrechoRecuperado]:
        """Reordena quando há reordenador. Falha volta à ordem vetorial.

        A recuperação não pode cair porque um modelo opcional tropeçou — mesma
        disciplina da mediação.
        """
        if self._reordenador is None or not self._config.reordenar or not trechos:
            return trechos
        try:
            return self._reordenador.reordenar(pergunta, trechos)
        except (ErroPipeline, RuntimeError, ValueError):
            return trechos

    def buscar(self, pergunta: str, k: int | None = None) -> list[TrechoRecuperado]:
        """Trechos mais próximos da pergunta, do mais para o menos similar.

        Busca direta, uma consulta e um vetor. A decomposição de pergunta
        composta em N sub-consultas vive em `rag.mediacao`, envolvendo esta
        classe por injeção — não aqui dentro. É o que mantém esta etapa como a
        linha de base contra a qual a mediação é comparável
        (`buscar --sem-intermediar`).
        """
        vetor = self._embutidor.embutir([pergunta])[0]
        candidatos = self._repositorio.buscar(
            vetor,
            k=self._quantos_candidatos(k),
            score_minimo=self._config.score_minimo,
        )
        candidatos = self._reordenar(pergunta, candidatos)

        return decidir_quantidade(
            candidatos,
            self._config,
            k,
            reordenados=self._reordenador is not None and self._config.reordenar,
        )
