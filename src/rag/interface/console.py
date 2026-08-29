"""
Saída e entrada no terminal.

Concentrar isso aqui é o que permite às etapas relatarem progresso sem saber
como ele é exibido — e o que torna possível trocar o console por outra
interface (web, API) sem reescrever o pipeline.

As cores são desligadas automaticamente quando a saída não é um terminal
(redirecionamento para arquivo, `| less`, execução por outro programa), senão
os códigos ANSI apareceriam como lixo no meio do texto.
"""

import shutil
import sys
import time

_COLORIR = sys.stdout.isatty()


def _cor(codigo: str) -> str:
    return codigo if _COLORIR else ""


NEGRITO = _cor("\033[1m")
APAGADO = _cor("\033[2m")
VERDE = _cor("\033[32m")
AMARELO = _cor("\033[33m")
VERMELHO = _cor("\033[31m")
AZUL = _cor("\033[36m")
NORMAL = _cor("\033[0m")

LARGURA = min(shutil.get_terminal_size((80, 24)).columns, 100)


def largura_util() -> int:
    return LARGURA


def desligar_cores() -> None:
    """Remove os códigos ANSI da saída (opção --sem-cor).

    Reatribui os nomes no próprio módulo porque eles são lidos como
    `console.NEGRITO` pelos chamadores — trocar aqui vale para todos.
    """
    global NEGRITO, APAGADO, VERDE, AMARELO, VERMELHO, AZUL, NORMAL, _COLORIR
    _COLORIR = False
    NEGRITO = APAGADO = VERDE = AMARELO = VERMELHO = AZUL = NORMAL = ""


# ── saída ─────────────────────────────────────────────────────────────────


def titulo(texto: str) -> None:
    print(f"\n{NEGRITO}{texto}{NORMAL}")
    print(f"{APAGADO}{'─' * min(len(texto), LARGURA)}{NORMAL}")


def secao(texto: str) -> None:
    print(f"\n{NEGRITO}{AZUL}{texto}{NORMAL}")


def info(texto: str = "") -> None:
    print(texto)


def detalhe(texto: str) -> None:
    print(f"{APAGADO}{texto}{NORMAL}")


def sucesso(texto: str) -> None:
    print(f"{VERDE}✓{NORMAL} {texto}")


def aviso(texto: str) -> None:
    print(f"{AMARELO}!{NORMAL} {texto}")


def falha(texto: str) -> None:
    print(f"{VERMELHO}✗{NORMAL} {texto}")


def erro_do_pipeline(erro: Exception, sugestao: str = "") -> None:
    """Erro conhecido: mensagem e conserto, sem traceback."""
    falha(str(erro))
    sugestao = sugestao or getattr(erro, "sugestao", "")
    if sugestao:
        detalhe(f"  → {sugestao}")


class Progresso:
    """Barra de progresso para as etapas longas.

    Redesenha na mesma linha com `\\r` quando há terminal; fora dele, imprime
    uma linha a cada atualização relevante, para que a saída continue legível
    em log ou redirecionamento.
    """

    def __init__(self, rotulo: str, intervalo_minimo: float = 0.1) -> None:
        self._rotulo = rotulo
        self._intervalo = intervalo_minimo
        self._ultimo = 0.0
        self._inicio = time.monotonic()

    def __call__(self, feito: int, total: int, extra: str = "") -> None:
        agora = time.monotonic()
        final = total and feito >= total
        if not final and agora - self._ultimo < self._intervalo:
            return
        self._ultimo = agora

        decorrido = agora - self._inicio
        proporcao = (feito / total) if total else 0.0
        largura_barra = 28
        cheio = int(proporcao * largura_barra)
        barra = "█" * cheio + "░" * (largura_barra - cheio)
        linha = f"  {self._rotulo} [{barra}] {proporcao:5.1%}  {extra}  {APAGADO}{decorrido:.0f}s{NORMAL}"

        if _COLORIR:
            print(f"\r{linha[: LARGURA + 20]}", end="", flush=True)
            if final:
                print()
        elif final or int(decorrido) % 10 == 0:
            print(linha.strip())

    def encerrar(self) -> None:
        if _COLORIR:
            print()


# ── entrada ───────────────────────────────────────────────────────────────


def perguntar(rotulo: str, padrao: str = "") -> str:
    """Lê uma linha. Devolve o padrão quando o usuário só aperta Enter.

    KeyboardInterrupt e EOF viram string vazia: nas duas situações o usuário
    está pedindo para sair do prompt, e quem chamou trata isso como "voltar".
    """
    sufixo = f" {APAGADO}[{padrao}]{NORMAL}" if padrao else ""
    try:
        resposta = input(f"{NEGRITO}{rotulo}{NORMAL}{sufixo}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return ""
    return resposta or padrao


def confirmar(rotulo: str, padrao: bool = False) -> bool:
    """Pergunta de sim/não. Usada antes de tudo que é caro ou destrutivo."""
    opcoes = "S/n" if padrao else "s/N"
    resposta = perguntar(f"{rotulo} ({opcoes})").lower()
    if not resposta:
        return padrao
    return resposta in {"s", "sim", "y", "yes"}


def habilitar_historico() -> None:
    """Liga edição de linha e histórico nos prompts, quando disponível.

    Sem isso, digitar uma pergunta longa e errar uma palavra no meio obriga a
    apagar tudo — as setas viram sequências de escape literais.
    """
    try:
        import readline  # noqa: F401
    except ImportError:
        pass  # Windows sem pyreadline: os prompts funcionam, só sem histórico


class EscritorFluido:
    """Imprime texto que chega em pedaços, quebrando linha na largura do terminal.

    O Ollama entrega a resposta em fragmentos que não respeitam limite de
    palavra ("Argo", "nianos", " são"). Jogá-los direto no `print` produz
    quebras no meio de palavra assim que a linha estoura a largura. Aqui a
    palavra é segurada até se saber se ela cabe.
    """

    def __init__(self, margem: int = 2) -> None:
        self._margem = margem
        self._coluna = margem
        self._pendente = ""
        self._comecou = False

    def escrever(self, pedaco: str) -> None:
        for caractere in pedaco:
            if caractere == "\n":
                self._descarregar()
                print()
                self._coluna = self._margem
                self._comecou = False
            elif caractere.isspace():
                self._descarregar()
                if self._comecou and self._coluna < LARGURA:
                    print(" ", end="", flush=True)
                    self._coluna += 1
            else:
                self._pendente += caractere

    def _descarregar(self) -> None:
        if not self._pendente:
            return
        palavra = self._pendente
        self._pendente = ""

        if self._comecou and self._coluna + len(palavra) > LARGURA:
            print()
            self._coluna = self._margem
            print(" " * self._margem, end="")
        elif not self._comecou:
            print(" " * self._margem, end="")

        print(palavra, end="", flush=True)
        self._coluna += len(palavra)
        self._comecou = True

    def encerrar(self) -> None:
        self._descarregar()
        print()
