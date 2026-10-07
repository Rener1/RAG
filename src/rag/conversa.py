"""
Memória de conversa — um seguimento entendido à luz do que veio antes.

Sem isto, cada pergunta chega sozinha. "E os Khajiit?" vai à busca como
"e os Khajiit?", e "quem era o líder deles?" não tem referente nenhum: nem o
embedding nem o modelo sabem de quem se fala.

Duas peças, com papéis diferentes:

- **Reescrita antes da busca.** Com histórico, uma chamada ao modelo transforma
  o seguimento numa pergunta que se sustenta sozinha. Ela segue o caminho de
  sempre — triagem, mediação, busca — e nenhuma camada abaixo precisa saber que
  existe conversa. Sem histórico, não há chamada.
- **Histórico no prompt da resposta.** Para referências à própria resposta
  ("explique melhor o ponto 2"), que a busca não resolve. Entra no overhead do
  orçamento de contexto, então ocupa espaço dos trechos de forma explícita.

O risco principal é **contaminação**: puxar para o assunto anterior uma pergunta
que mudou de assunto. O prompt manda devolver intacta a pergunta que já se
entende sozinha, e o gabarito de conversa tem casos de troca de assunto para
medir exatamente isso.

Mora na raiz do pacote, como `mediacao.py` e `sessao.py`: compõe geração com
recuperação, e isso não pertence a nenhuma etapa. O histórico vive só na
memória do processo.
"""

from dataclasses import dataclass

from .config import ConfigConversa
from .erros import ErroPipeline
from .modelos import TrocaDaConversa
from .protocolos import Gerador

# Uma reescrita muito maior que a pergunta é o modelo respondendo em vez de
# reescrever, ou acrescentando o histórico inteiro. Nos dois casos, a pergunta
# crua busca melhor que o resultado.
FATOR_MAXIMO_DE_CRESCIMENTO = 4
FOLGA_MINIMA_DE_CARACTERES = 160

# Quanto da resposta anterior a reescrita enxerga. É só para resolver
# referências ("o segundo ponto", "esse autor"), não para resumir a conversa.
CARACTERES_DA_RESPOSTA_NA_REESCRITA = 400


@dataclass(frozen=True, slots=True)
class Reescrita:
    """O que foi à busca no lugar da pergunta, e por quê."""

    original: str
    consulta: str
    veio_do_modelo: bool = False
    motivo: str = ""

    @property
    def mudou(self) -> bool:
        return self.consulta.strip() != self.original.strip()


def _truncar(texto: str, limite: int) -> str:
    texto = " ".join(texto.split())
    return texto if len(texto) <= limite else texto[:limite].rstrip() + "…"


def montar_prompt_de_reescrita(trocas: list[TrocaDaConversa], pergunta: str) -> str:
    """Prompt que torna o seguimento autônomo — ou o devolve intacto.

    Os exemplos são do domínio do acervo real, não da lore, para não precisarem
    mudar na troca de corpus. O segundo é o que importa mais: ensina a **não**
    reescrever quando o assunto mudou.
    """
    linhas: list[str] = []
    for troca in trocas:
        linhas.append(f"pessoa: {troca.consulta}")
    if trocas and trocas[-1].resposta:
        linhas.append(
            f"sistema (início da resposta): {_truncar(trocas[-1].resposta, CARACTERES_DA_RESPOSTA_NA_REESCRITA)}"
        )
    historico = "\n".join(linhas)

    return f"""Você recebe o histórico de uma conversa e a nova mensagem de quem pergunta.

Reescreva a nova mensagem como uma pergunta completa, que se entenda sem o histórico: \
troque pronomes e referências ("deles", "isso", "e os outros?", "o segundo ponto") \
pelo assunto a que se referem.

Se a nova mensagem já se entende sozinha, ou muda de assunto, devolva-a exatamente \
como está, sem acrescentar nada do histórico.

Mantenha os nomes próprios como estão escritos. Responda só com a pergunta, numa \
linha, sem comentário.

Exemplos:

  histórico: quem escreveu Pedagogia do Oprimido?
  nova: e quando foi publicado?
  -> quando foi publicado o livro Pedagogia do Oprimido?

  histórico: quem escreveu Pedagogia do Oprimido?
  nova: o que é um tema gerador?
  -> o que é um tema gerador?

HISTÓRICO:
{historico}

NOVA MENSAGEM:
{pergunta}
"""


def extrair_reescrita(saida_do_modelo: str, pergunta: str) -> str:
    """A primeira linha útil da saída, ou vazio se ela não servir.

    Aceita os enfeites que o modelo costuma pôr (seta, aspas, rótulo) e
    descarta o que não é uma reescrita plausível. Vazio significa "use a
    pergunta crua" — quem decide o fallback é a `Conversa`.
    """
    for linha in saida_do_modelo.splitlines():
        texto = linha.strip().lstrip("->•*").strip()
        for rotulo in ("nova:", "pergunta:", "reescrita:"):
            if texto.casefold().startswith(rotulo):
                texto = texto[len(rotulo) :].strip()
        texto = texto.strip("\"'“”").strip()
        if not texto:
            continue
        teto = max(len(pergunta) * FATOR_MAXIMO_DE_CRESCIMENTO, len(pergunta) + FOLGA_MINIMA_DE_CARACTERES)
        return texto if len(texto) <= teto else ""
    return ""


def formatar_historico(trocas: list[TrocaDaConversa], caracteres_por_resposta: int) -> str:
    """O bloco de conversa anterior que vai ao prompt da resposta."""
    blocos: list[str] = []
    for troca in trocas:
        bloco = f"Pergunta: {troca.pergunta}"
        if troca.resposta:
            bloco += f"\nResposta: {_truncar(troca.resposta, caracteres_por_resposta)}"
        blocos.append(bloco)
    return "\n\n".join(blocos)


class Conversa:
    """O histórico de uma conversa e o que se faz com ele.

    Não imprime nada e não conduz laço nenhum: quem lê a linha e mostra a
    reescrita é a interface. Nunca levanta — tropeço na reescrita vira a pergunta
    crua, porque a conversa é uma camada por cima do ciclo RAG e não pode ser o
    motivo de ninguém conseguir perguntar.
    """

    def __init__(self, gerador: Gerador, config: ConfigConversa) -> None:
        self._gerador = gerador
        self._config = config
        self.trocas: list[TrocaDaConversa] = []

    @property
    def vazia(self) -> bool:
        return not self.trocas

    def _lembradas(self) -> list[TrocaDaConversa]:
        return self.trocas[-self._config.turnos_lembrados :] if self._config.turnos_lembrados > 0 else []

    def reescrever(self, pergunta: str) -> Reescrita:
        """A pergunta como deve ir à busca."""
        lembradas = self._lembradas()
        if not lembradas:
            return Reescrita(pergunta, pergunta, motivo="primeira pergunta da conversa")

        try:
            saida = "".join(self._gerador.gerar(montar_prompt_de_reescrita(lembradas, pergunta)))
        except ErroPipeline as erro:
            return Reescrita(pergunta, pergunta, motivo=f"o modelo não respondeu ({erro.mensagem})")

        consulta = extrair_reescrita(saida, pergunta)
        if not consulta:
            return Reescrita(pergunta, pergunta, motivo="o modelo não devolveu reescrita aproveitável")
        return Reescrita(pergunta, consulta, veio_do_modelo=True)

    def registrar(self, pergunta: str, consulta: str, resposta: str = "") -> None:
        self.trocas.append(TrocaDaConversa(pergunta=pergunta, consulta=consulta, resposta=resposta))
        # Guarda só o que alguém vai ler: a reescrita e o prompt usam as últimas.
        manter = max(self._config.turnos_lembrados, self._config.turnos_no_prompt)
        if len(self.trocas) > manter:
            self.trocas = self.trocas[-manter:]

    def historico_para_o_prompt(self) -> str:
        """Vazio quando não há o que mostrar — e o prompt fica igual ao de sempre."""
        if self._config.turnos_no_prompt <= 0:
            return ""
        trocas = self.trocas[-self._config.turnos_no_prompt :]
        return formatar_historico(trocas, self._config.caracteres_por_resposta)

    def zerar(self) -> None:
        self.trocas = []

    @classmethod
    def com_perguntas_anteriores(cls, gerador: Gerador, config: ConfigConversa, perguntas: list[str]) -> "Conversa":
        """Conversa já com histórico, sem respostas — é o que a avaliação usa.

        A avaliação mede recuperação sem gerar resposta, então os turnos
        anteriores entram só como perguntas. As do gabarito já são autônomas,
        e por isso entram como consulta também.
        """
        conversa = cls(gerador, config)
        for pergunta in perguntas:
            conversa.registrar(pergunta, pergunta)
        return conversa
