"""
Sessão dialógica — a máquina de estados que problematiza antes de responder.

O fluxo padrão deste sistema não é pergunta→resposta. É pergunta→devolução de
perguntas→construção conjunta (`docs/fase-2-prototipo.md` §4.6). A razão é de
forma, não de conteúdo: um sistema que recebe uma demanda e devolve o produto
pronto é educação bancária automatizada, e o conteúdo diria Freire enquanto a
forma diria o contrário.

Nem toda pergunta merece esse tratamento, e é isso que a triagem decide. Dúvida
factual atalha direto para a busca; pedido de produto acabado e exploração
passam pela problematização. Quem pergunta pode sempre pular.

O ganho não é só de forma: o que a pessoa responde entra na consulta que vai à
recuperação (`Sessao.consulta_consolidada`), então problematizar melhora a busca
também. Se a mediação estiver ligada, é esse texto consolidado que ela decompõe
— as duas camadas se compõem sem que nenhuma conheça a outra.

Mora na raiz do pacote, e não em `etapas/`, pelo mesmo motivo do orquestrador:
amarra recuperação com geração. Os textos que orientam o modelo vêm do marco,
não daqui.
"""

from collections.abc import Iterator

from .config import ConfigSessao
from .erros import ErroPipeline

# Tirar numeração e marcador da saída do modelo é o mesmo problema aqui e na
# mediação — duas cópias da mesma expressão divergiriam no primeiro ajuste.
from .mediacao import PADRAO_MARCADOR
from .modelos import EstadoDaSessao, Sessao, TipoDeDemanda, TrechoRecuperado
from .orquestrador import MotorRag
from .protocolos import Gerador, MarcoPedagogico

# Palavras que a pessoa digita para seguir sem responder. Existem porque a
# problematização só é dialógica se recusá-la for tão fácil quanto aceitá-la.
PALAVRAS_DE_ESCAPE = {"pular", "seguir", "responder", "/pular", "/seguir", "/responder"}

# Heurística determinística de triagem. Serve de rede quando o modelo devolve
# algo irreconhecível, e é o que permite testar a máquina inteira sem Ollama.
PISTAS_DE_PRODUTO = (
    "faça",
    "faca ",
    "monte",
    "escreva",
    "elabore",
    "redija",
    "crie",
    "formule",
    "gere um",
    "gere uma",
    "modelo de",
    "me dê pronto",
    "minuta",
)
PISTAS_FACTUAIS = (
    "o que é",
    "o que foi",
    "o que são",
    "quem é",
    "quem foi",
    "quem são",
    "quando",
    "quantos",
    "quantas",
    "onde fica",
    "qual o significado",
    "qual é a definição",
)

K_PARA_ANCORAR = 4  # trechos que alimentam o prompt de problematização

TAMANHO_MINIMO_DE_PERGUNTA = 10
TAMANHO_MAXIMO_DE_PERGUNTA = 300


def classificar_por_pistas(pergunta: str) -> TipoDeDemanda:
    """Triagem sem modelo, por expressões de abertura.

    O pedido de produto acabado é checado antes da dúvida factual porque "o que
    é X" dentro de "escreva um relatório sobre o que é X" continua sendo pedido
    de produto — a forma verbal do começo manda.
    """
    texto = pergunta.strip().casefold()

    if any(texto.startswith(pista) or f" {pista}" in texto for pista in PISTAS_DE_PRODUTO):
        return TipoDeDemanda.PRODUTO_ACABADO
    if any(texto.startswith(pista) for pista in PISTAS_FACTUAIS):
        return TipoDeDemanda.DUVIDA_FACTUAL
    return TipoDeDemanda.INDEFINIDO


def montar_prompt_de_triagem(pergunta: str, orientacao: str = "") -> str:
    extra = f"\n\nComo distinguir, neste acervo:\n{orientacao}" if orientacao.strip() else ""

    return f"""Classifique a demanda abaixo em exatamente uma destas três palavras:

produto_acabado — pede um documento, plano, texto ou material pronto para entregar
duvida_factual — pergunta por um fato, uma data, uma definição ou quem é alguém
exploracao — quer investigar um assunto amplo, sem uma resposta única{extra}

Responda com a palavra, e nada mais.

DEMANDA:
{pergunta}
"""


def ler_demanda(saida_do_modelo: str) -> TipoDeDemanda:
    """A palavra que o modelo devolveu, ou INDEFINIDO se não deu para saber."""
    texto = saida_do_modelo.strip().casefold()

    for tipo in (TipoDeDemanda.PRODUTO_ACABADO, TipoDeDemanda.DUVIDA_FACTUAL, TipoDeDemanda.EXPLORACAO):
        if tipo.value in texto or tipo.value.replace("_", " ") in texto:
            return tipo
    return TipoDeDemanda.INDEFINIDO


def montar_prompt_de_problematizacao(
    demanda: str,
    maximo: int,
    orientacao: str = "",
    trechos: list[TrechoRecuperado] | None = None,
) -> str:
    """Prompt das perguntas devolvidas.

    Os trechos entram para as perguntas serem sobre o que o acervo tem a dizer,
    e não genéricas. É a mitigação direta do modo de falha central destes
    documentos: vocabulário militante bem articulado, aplicado sem ancoragem no
    território concreto e sem consequência prática
    (`docs/fase-3-avaliacao-e-servidor.md` §3).
    """
    extra = f"\n\nOrientação:\n{orientacao}" if orientacao.strip() else ""

    contexto = ""
    if trechos:
        material = "\n\n".join(f"- {trecho.titulo_pagina}: {trecho.previa(300)}" for trecho in trechos)
        contexto = (
            "\n\nO acervo tem material sobre isto. Use-o para que as perguntas "
            f"sejam concretas, e não genéricas:\n{material}"
        )

    return f"""Antes de responder, devolva até {maximo} perguntas a quem fez a demanda abaixo.

As perguntas servem para construir a resposta junto, não para adiar o trabalho.
Pergunte o que só quem fez a demanda sabe — o contexto, os sujeitos envolvidos, o
recorte pretendido — e nunca o que o acervo já responderia.

Regras:
- Uma pergunta por linha, e nada mais na resposta.
- Sem numeração, sem marcador, sem introdução, sem comentário.
- Se a demanda já estiver clara o bastante para ser respondida, não devolva nada.{extra}{contexto}

DEMANDA:
{demanda}
"""


def extrair_perguntas(saida_do_modelo: str, maximo: int) -> list[str]:
    """As perguntas devolvidas pelo modelo. Linha sem '?' não é pergunta."""
    perguntas: list[str] = []
    vistas: set[str] = set()

    for linha in saida_do_modelo.splitlines():
        texto = PADRAO_MARCADOR.sub("", linha).strip().strip('"').strip()
        if "?" not in texto or not TAMANHO_MINIMO_DE_PERGUNTA <= len(texto) <= TAMANHO_MAXIMO_DE_PERGUNTA:
            continue

        comparavel = texto.casefold()
        if comparavel in vistas:
            continue

        vistas.add(comparavel)
        perguntas.append(texto)
        if len(perguntas) >= maximo:
            break

    return perguntas


class Dialogo:
    """A máquina de estados. Não imprime nada: quem conduz o laço é a interface.

    Transições:

        iniciar()  ──> TRIAGEM
           ├─ problematização desligada, ou demanda factual ──> RECUPERACAO
           └─ produto acabado / exploração / indefinido ────> PROBLEMATIZACAO
                                                                  │
                    receber() com resposta e rodadas esgotadas ───┤
                    receber() vazio, ou pular_problematizacao() ──┤
                    modelo não devolveu pergunta nenhuma ─────────┴──> RECUPERACAO
                                                                          │
                                       responder(), com trechos ──> RESPOSTA ──> ENCERRADA
                                       responder(), sem trechos ─────────────> ENCERRADA
    """

    def __init__(
        self,
        motor: MotorRag,
        gerador: Gerador,
        config: ConfigSessao,
        marco: MarcoPedagogico | None = None,
    ) -> None:
        self._motor = motor
        self._gerador = gerador
        self._config = config
        self._marco = marco

    # ── apoio ─────────────────────────────────────────────────────────────

    def _secao(self, nome: str) -> str:
        return self._marco.secao(nome) if self._marco else ""

    def _uma_resposta(self, prompt: str) -> str:
        """Chamada única ao modelo. Devolve vazio em vez de propagar erro.

        A sessão é uma camada por cima do ciclo RAG: se ela cair, a resposta
        ainda tem de sair. Um classificador fora do ar não pode ser motivo para
        ninguém conseguir perguntar nada.
        """
        try:
            return "".join(self._gerador.gerar(prompt))
        except ErroPipeline:
            return ""

    def problematizacao_habilitada(self) -> bool:
        """A configuração liga, e o marco pode desligar — nunca o contrário.

        Um marco que não é dialógico não devolve perguntas só porque a
        configuração da máquina está ligada; e ligar pelo marco um sistema que
        o operador desligou seria a máquina passando por cima da pessoa.
        """
        if not self._config.problematizar:
            return False
        if self._marco is None:
            return True
        return self._marco.diz_sim("problematizar", padrao=True)

    # ── estados ───────────────────────────────────────────────────────────

    def iniciar(self, pergunta: str) -> Sessao:
        sessao = Sessao(pergunta_inicial=pergunta)
        sessao.registrar("pessoa", pergunta)
        return sessao

    def classificar(self, sessao: Sessao) -> TipoDeDemanda:
        """Decide o tipo de demanda e para onde a sessão vai.

        Com a problematização desligada nem chama o modelo: pagar por uma
        classificação sobre a qual não se vai agir é só latência.
        """
        if not self.problematizacao_habilitada():
            sessao.estado = EstadoDaSessao.RECUPERACAO
            return sessao.demanda

        por_pistas = classificar_por_pistas(sessao.pergunta_inicial)

        demanda = TipoDeDemanda.INDEFINIDO
        if self._config.classificar_com_modelo:
            prompt = montar_prompt_de_triagem(sessao.pergunta_inicial, self._secao("triagem"))
            demanda = ler_demanda(self._uma_resposta(prompt))

        # "Escreva um relatório sobre X" é pedido de produto acabado por
        # construção da frase, e a diretriz que mais importa aqui é justamente a
        # de não entregar produto pronto. Quando a heurística reconhece essa
        # forma, ela vence o modelo: o custo de problematizar à toa é um Enter,
        # e o de deixar passar é o sistema fazer exatamente o que foi desenhado
        # para não fazer.
        if por_pistas is TipoDeDemanda.PRODUTO_ACABADO:
            demanda = por_pistas
        elif demanda is TipoDeDemanda.INDEFINIDO:
            demanda = por_pistas

        sessao.demanda = demanda
        # INDEFINIDO cai na problematização: diante de dúvida, o desenho erra
        # para o lado do diálogo — e pular custa um Enter.
        sessao.estado = (
            EstadoDaSessao.RECUPERACAO if demanda is TipoDeDemanda.DUVIDA_FACTUAL else EstadoDaSessao.PROBLEMATIZACAO
        )
        return demanda

    def problematizar(self, sessao: Sessao) -> list[str]:
        """Perguntas a devolver. Lista vazia significa 'siga para a busca'."""
        if sessao.estado is not EstadoDaSessao.PROBLEMATIZACAO:
            return []

        trechos: list[TrechoRecuperado] = []
        if self._config.perguntas_ancoradas:
            try:
                trechos = self._motor.recuperar(sessao.consulta_consolidada(), k=K_PARA_ANCORAR)
            except ErroPipeline:
                trechos = []

        prompt = montar_prompt_de_problematizacao(
            sessao.consulta_consolidada(),
            self._config.maximo_de_perguntas,
            self._secao("problematizacao"),
            trechos,
        )
        perguntas = extrair_perguntas(self._uma_resposta(prompt), self._config.maximo_de_perguntas)

        if not perguntas:
            sessao.estado = EstadoDaSessao.RECUPERACAO
            return []

        sessao.rodadas_de_problematizacao += 1
        for pergunta in perguntas:
            sessao.registrar("sistema", pergunta)
        return perguntas

    def receber(self, sessao: Sessao, texto: str) -> EstadoDaSessao:
        """Registra o que a pessoa respondeu e decide se há outra rodada."""
        resposta = texto.strip()

        if not resposta or resposta.casefold() in PALAVRAS_DE_ESCAPE:
            sessao.estado = EstadoDaSessao.RECUPERACAO
            return sessao.estado

        sessao.registrar("pessoa", resposta)
        if sessao.rodadas_de_problematizacao >= self._config.maximo_de_rodadas:
            sessao.estado = EstadoDaSessao.RECUPERACAO
        return sessao.estado

    def pular_problematizacao(self, sessao: Sessao) -> None:
        """Segue para a busca mantendo o que já foi dito."""
        sessao.estado = EstadoDaSessao.RECUPERACAO

    def responder(
        self,
        sessao: Sessao,
        k: int | None = None,
        historico: str = "",
    ) -> tuple[list[TrechoRecuperado], Iterator[str]]:
        """Fecha o ciclo com a consulta consolidada, não com a pergunta crua."""
        trechos, fluxo = self._motor.responder_em_fluxo(sessao.consulta_consolidada(), k=k, historico=historico)
        sessao.estado = EstadoDaSessao.RESPOSTA if trechos else EstadoDaSessao.ENCERRADA
        return trechos, fluxo

    def encerrar(self, sessao: Sessao) -> None:
        sessao.estado = EstadoDaSessao.ENCERRADA
