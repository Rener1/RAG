"""
Linha de comando.

Mesmo conjunto de funcionalidades do menu, chamável de script — necessário
para automação (as skills do projeto, um cron, um Makefile) e para repetir uma
etapa sem navegar por menu.

Sem subcomando, abre o menu interativo: é o caminho esperado de quem só rodou
`python3 main.py`.
"""

import argparse
import sys

from ..config import CONFIG, Config
from ..erros import ErroPipeline
from ..servico import Servico
from . import acoes, console, menu

DESCRICAO = """\
Pipeline RAG local do projeto IA Freiriana.

Sem subcomando, abre o menu interativo com todas as etapas.
"""

EXEMPLOS = """\
exemplos:
  python3 main.py                          menu interativo
  python3 main.py ambiente                 diagnóstico do ambiente
  python3 main.py chunking                 refaz os chunks
  python3 main.py indexar --recriar        reindexa do zero
  python3 main.py buscar "quem são os argonianos?"
  python3 main.py perguntar "o que foi a crise de oblivion?" --k 8
  python3 main.py perguntar                modo conversa, uma pergunta por linha
"""


def construir_parser() -> argparse.ArgumentParser:
    # As opções globais entram também em cada subcomando (`parents`), senão o
    # argparse só as aceita antes do comando — e `main.py ambiente --sem-cor`,
    # que é como se escreve naturalmente, viraria erro de sintaxe.
    globais = argparse.ArgumentParser(add_help=False)
    globais.add_argument("--colecao", help="coleção do banco vetorial a usar nesta execução")
    globais.add_argument("--sem-cor", action="store_true", help="desliga as cores da saída")

    parser = argparse.ArgumentParser(
        prog="main.py",
        description=DESCRICAO,
        epilog=EXEMPLOS,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        parents=[globais],
    )

    sub = parser.add_subparsers(dest="comando", metavar="comando")

    def novo_subcomando(nome: str, ajuda: str) -> argparse.ArgumentParser:
        return sub.add_parser(nome, help=ajuda, parents=[globais])

    novo_subcomando("ambiente", "diagnostica serviços, modelos e artefatos")
    novo_subcomando("baixar", "etapa 1 — baixa o corpus (demorado)")

    p_chunking = novo_subcomando("chunking", "etapa 2 — corta o corpus em trechos")
    p_chunking.add_argument("--estrategia", help="estratégia de corte (paragrafo, paragrafo_agrupado)")

    p_indexar = novo_subcomando("indexar", "etapa 3 — embedding e indexação (muito demorado)")
    p_indexar.add_argument("--recriar", action="store_true", help="apaga a coleção e indexa do zero")
    p_indexar.add_argument("--sem-retomada", action="store_true", help="não pula os chunks já indexados")

    for nome, ajuda in (("buscar", "etapa 4 — só recuperação"), ("perguntar", "etapa 5 — ciclo RAG completo")):
        p = novo_subcomando(nome, ajuda)
        p.add_argument("pergunta", nargs="*", help="a pergunta; sem ela, entra em modo conversa")
        p.add_argument("--k", type=int, help="quantos trechos recuperar")

    novo_subcomando("config", "mostra a configuração em vigor")
    novo_subcomando("menu", "abre o menu interativo (padrão)")

    return parser


def _aplicar_opcoes_globais(argumentos: argparse.Namespace, config: Config) -> None:
    """Sobrescreve configuração para esta execução, antes de qualquer cliente subir."""
    if argumentos.colecao:
        config.vetorial.colecao = argumentos.colecao
    if getattr(argumentos, "estrategia", None):
        config.chunking.estrategia = argumentos.estrategia
    if argumentos.sem_cor:
        console.desligar_cores()


def _consultar(servico: Servico, argumentos: argparse.Namespace, modo: str) -> bool:
    """Uma pergunta vinda dos argumentos, ou o modo conversa quando não vier."""
    pergunta = " ".join(argumentos.pergunta).strip()
    executar_uma = acoes.acao_buscar if modo == "buscar" else acoes.acao_perguntar

    if pergunta:
        return executar_uma(servico, pergunta, k=argumentos.k)

    console.habilitar_historico()
    console.titulo("Modo conversa" + (" — busca" if modo == "buscar" else ""))
    console.detalhe("Uma pergunta por linha. Linha vazia encerra.")
    while True:
        pergunta = console.perguntar("\npergunta")
        if not pergunta:
            # Sair da conversa é uso normal, não falha — o modo conversa
            # sempre termina em sucesso.
            return True
        executar_uma(servico, pergunta, k=argumentos.k)


def principal(argv: list[str] | None = None) -> int:
    """Ponto de entrada. Devolve o código de saída do processo."""
    parser = construir_parser()
    argumentos = parser.parse_args(argv)

    config = CONFIG
    _aplicar_opcoes_globais(argumentos, config)
    servico = Servico(config)

    comando = argumentos.comando or "menu"

    try:
        if comando == "menu":
            return menu.executar(servico)
        if comando == "ambiente":
            return 0 if acoes.acao_ambiente(servico) else 1
        if comando == "baixar":
            return 0 if acoes.acao_baixar(servico, interativo=sys.stdin.isatty()) else 1
        if comando == "chunking":
            return 0 if acoes.acao_chunking(servico, interativo=sys.stdin.isatty()) else 1
        if comando == "indexar":
            sucesso = acoes.acao_indexar(
                servico,
                interativo=sys.stdin.isatty(),
                recriar=argumentos.recriar,
                retomar=not argumentos.sem_retomada,
            )
            return 0 if sucesso else 1
        if comando in {"buscar", "perguntar"}:
            return 0 if _consultar(servico, argumentos, comando) else 1
        if comando == "config":
            acoes.acao_mostrar_config(config)
    except ErroPipeline as erro:
        console.erro_do_pipeline(erro)
        return 1
    except KeyboardInterrupt:
        console.aviso("\nInterrompido.")
        return 130

    return 0
