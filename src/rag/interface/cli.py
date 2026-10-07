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
from pathlib import Path

from .. import config as configuracao
from ..config import Config
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
  python3 main.py chunking --estrategia paragrafo_agrupado --saida data/experimento.jsonl
  python3 main.py indexar --recriar        reindexa do zero
  python3 main.py --carga reduzida indexar   poupa a placa — EXPERIMENTAL (ver docs/estado)
  python3 main.py --chunks experimento.jsonl --colecao experimento indexar
  python3 main.py buscar "quem são os argonianos?"
  python3 main.py buscar "..." --sem-intermediar    busca sem reformular a pergunta
  python3 main.py buscar "..." --k-dinamico 0.9    quantidade de trechos conforme a pergunta
  python3 main.py perguntar "o que foi a crise de oblivion?" --k 8
  python3 main.py perguntar                modo conversa, uma pergunta por linha, com memória
  python3 main.py perguntar "..." --direto  responde sem problematizar
  python3 main.py config --salvar          persiste a configuração atual em config.toml
  python3 main.py avaliar --comparar               mede a recuperação com e sem mediação
  python3 main.py avaliar --conversa               mede a memória de conversa nos seguimentos
  python3 main.py marcos                   lista os marcos pedagógicos
  python3 main.py --marco freiriano perguntar "..."
"""


def construir_parser() -> argparse.ArgumentParser:
    # As opções globais entram também em cada subcomando (`parents`), senão o
    # argparse só as aceita antes do comando — e `main.py ambiente --sem-cor`,
    # que é como se escreve naturalmente, viraria erro de sintaxe.
    #
    # `default=SUPPRESS` não é enfeite: o subparser parseia num namespace novo e
    # copia tudo por cima do namespace principal, então sem isso a mesma flag
    # escrita ANTES do subcomando (`main.py --colecao x buscar ...`) seria
    # sobrescrita pelo default do subcomando e sumiria sem erro nenhum. Com
    # SUPPRESS o atributo só existe quando a flag foi de fato escrita, e os
    # valores base vêm do `set_defaults` no fim desta função.
    globais = argparse.ArgumentParser(add_help=False)
    globais.add_argument(
        "--colecao",
        default=argparse.SUPPRESS,
        help="coleção do banco vetorial a usar nesta execução",
    )
    globais.add_argument(
        "--chunks",
        metavar="ARQUIVO",
        default=argparse.SUPPRESS,
        help="arquivo de chunks desta execução (relativo a data/); acompanha --colecao",
    )
    globais.add_argument(
        "--carga",
        choices=("total", "reduzida"),
        default=argparse.SUPPRESS,
        help="'total' (padrão) usa o hardware sem limite; 'reduzida' (EXPERIMENTAL) descansa entre lotes para poupá-lo",
    )
    globais.add_argument(
        "--config",
        type=Path,
        metavar="ARQUIVO",
        default=argparse.SUPPRESS,
        help="usa outro arquivo de configuração",
    )
    globais.add_argument(
        "--sem-config",
        action="store_true",
        default=argparse.SUPPRESS,
        help="ignora o config.toml e usa só os padrões",
    )
    globais.add_argument(
        "--marco",
        default=argparse.SUPPRESS,
        help="marco pedagógico a usar nesta execução (ver: main.py marcos)",
    )
    globais.add_argument(
        "--sem-cor",
        action="store_true",
        default=argparse.SUPPRESS,
        help="desliga as cores da saída",
    )

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
    p_chunking.add_argument("--tamanho-maximo", type=int, metavar="CHARS", help="teto de caracteres por chunk")
    p_chunking.add_argument(
        "--saida",
        type=Path,
        help="grava em outro arquivo, preservando o chunks.jsonl que corresponde ao índice",
    )

    p_indexar = novo_subcomando("indexar", "etapa 3 — embedding e indexação (muito demorado)")
    p_indexar.add_argument("--recriar", action="store_true", help="apaga a coleção e indexa do zero")
    p_indexar.add_argument("--sem-retomada", action="store_true", help="não pula os chunks já indexados")

    for nome, ajuda in (("buscar", "etapa 4 — só recuperação"), ("perguntar", "etapa 5 — ciclo RAG completo")):
        p = novo_subcomando(nome, ajuda)
        p.add_argument("pergunta", nargs="*", help="a pergunta; sem ela, entra em modo conversa")
        p.add_argument("--k", type=int, help="quantos trechos recuperar (fixo)")
        p.add_argument(
            "--k-dinamico",
            type=float,
            metavar="FRACAO",
            help="quantidade dinâmica: mantém o que pontuar acima desta fração do 1º colocado (ex.: 0.9)",
        )
        p.add_argument(
            "--sem-intermediar",
            action="store_true",
            help="busca a pergunta como foi escrita, sem reformular nem decompor",
        )
        p.add_argument("--reordenar", action="store_true", help="reordena os candidatos por cross-encoder")
        p.add_argument("--sem-reordenar", action="store_true", help="desliga a reordenação")
        p.add_argument("--hibrido", action="store_true", help="funde a busca densa com BM25 léxico")
        p.add_argument("--sem-hibrido", action="store_true", help="desliga a fusão léxica")
        p.add_argument(
            "--sem-memoria",
            action="store_true",
            help="no modo conversa, cada pergunta chega sozinha, sem o contexto das anteriores",
        )
        if nome == "perguntar":
            p.add_argument("--dialogo", action="store_true", help="força a problematização antes de responder")
            p.add_argument("--direto", action="store_true", help="responde de uma vez, sem problematizar")

    p_config = novo_subcomando("config", "mostra a configuração em vigor")
    p_config.add_argument("--salvar", action="store_true", help="grava em config.toml o que difere do padrão")
    p_config.add_argument("--caminho", action="store_true", help="imprime onde fica o arquivo de configuração")
    p_avaliar = novo_subcomando("avaliar", "mede a recuperação contra o gabarito (camada 4)")
    p_avaliar.add_argument("--k", type=int, help="quantos trechos recuperar por caso (fixo)")
    p_avaliar.add_argument(
        "--k-dinamico",
        type=float,
        metavar="FRACAO",
        help="mede a política de quantidade dinâmica em vez do k fixo",
    )
    p_avaliar.add_argument("--comparar", action="store_true", help="roda com e sem mediação e compara lado a lado")
    p_avaliar.add_argument(
        "--conversa",
        action="store_true",
        help="mede a memória de conversa: seguimento cru contra reescrito (avaliacao/casos_conversa.jsonl)",
    )
    p_avaliar.add_argument("--casos", help="outro gabarito (padrão: avaliacao/casos.jsonl)")
    p_avaliar.add_argument("--sem-intermediar", action="store_true", help="mede só a busca direta, sem mediação")
    p_avaliar.add_argument("--reordenar", action="store_true", help="mede com reordenação por cross-encoder")
    p_avaliar.add_argument("--sem-reordenar", action="store_true", help="mede sem reordenação")
    p_avaliar.add_argument("--hibrido", action="store_true", help="mede com fusão léxica BM25")
    p_avaliar.add_argument("--sem-hibrido", action="store_true", help="mede sem fusão léxica")

    p_acelerador = novo_subcomando("acelerador", "diz qual torch esta máquina precisa")
    p_acelerador.add_argument(
        "--indice",
        action="store_true",
        help="imprime só a URL do índice, para usar em --build-arg",
    )
    p_acelerador.add_argument(
        "--arquitetura",
        action="store_true",
        help="imprime só a arquitetura da GPU (ex.: gfx1201), para enxugar a imagem",
    )

    novo_subcomando("marcos", "lista os marcos pedagógicos disponíveis")
    novo_subcomando("menu", "abre o menu interativo (padrão)")

    return parser


# Contrapartida do SUPPRESS: os atributos precisam existir mesmo quando a flag
# não foi escrita. Não dá para usar `parser.set_defaults` aqui — ele reescreve o
# `default` do objeto da ação, que `parents` compartilha entre o parser principal
# e todos os subcomandos, desfazendo justamente o SUPPRESS que resolve o problema.
GLOBAIS_PADRAO = {
    "colecao": None,
    "chunks": None,
    "carga": None,
    "config": None,
    "sem_config": False,
    "marco": None,
    "sem_cor": False,
}


def _normalizar_globais(argumentos: argparse.Namespace) -> None:
    for nome, padrao in GLOBAIS_PADRAO.items():
        if not hasattr(argumentos, nome):
            setattr(argumentos, nome, padrao)


def _aplicar_opcoes_globais(argumentos: argparse.Namespace, config: Config) -> None:
    """Sobrescreve configuração para esta execução, antes de qualquer cliente subir."""
    if argumentos.colecao:
        config.vetorial.colecao = argumentos.colecao
    if argumentos.chunks:
        config.caminhos.arquivo_chunks = argumentos.chunks
    if argumentos.carga is not None:
        config.carga.modo = argumentos.carga
    if argumentos.marco is not None:
        config.marco.ativo = argumentos.marco
    if getattr(argumentos, "estrategia", None):
        config.chunking.estrategia = argumentos.estrategia
    if getattr(argumentos, "tamanho_maximo", None):
        config.chunking.tamanho_maximo = argumentos.tamanho_maximo
    if getattr(argumentos, "sem_intermediar", False):
        config.intermediacao.ligada = False
    if getattr(argumentos, "k_dinamico", None) is not None:
        config.busca.limiar_relativo = argumentos.k_dinamico
    if getattr(argumentos, "reordenar", False):
        config.busca.reordenar = True
    if getattr(argumentos, "sem_reordenar", False):
        config.busca.reordenar = False
    if getattr(argumentos, "hibrido", False):
        config.busca.hibrido = True
    if getattr(argumentos, "sem_hibrido", False):
        config.busca.hibrido = False
    if getattr(argumentos, "sem_memoria", False):
        config.conversa.ligada = False
    if argumentos.sem_cor:
        console.desligar_cores()


def _escolher_modo_de_pergunta(servico: Servico, argumentos: argparse.Namespace) -> bool:
    """Decide entre o ciclo direto e a sessão dialógica.

    Sem terminal a sessão nunca roda, mesmo com `--dialogo`: as perguntas
    devolvidas não teriam para quem ir, e o processo ficaria pendurado num
    `input()` que nunca é atendido. É essa linha que mantém
    `main.py perguntar "..."` funcionando em cron, pipe e script.
    """
    if argumentos.direto:
        return False

    quer_dialogo = argumentos.dialogo or servico.config.sessao.problematizar
    if quer_dialogo and not sys.stdin.isatty():
        if argumentos.dialogo:
            console.aviso("Sem terminal interativo: respondendo direto, sem problematizar.")
        return False

    return quer_dialogo


def _consultar(servico: Servico, argumentos: argparse.Namespace, modo: str) -> bool:
    """Uma pergunta vinda dos argumentos, ou o modo conversa quando não vier."""
    pergunta = " ".join(argumentos.pergunta).strip()

    if modo == "buscar":
        executar_uma = acoes.acao_buscar
    elif _escolher_modo_de_pergunta(servico, argumentos):
        executar_uma = acoes.acao_dialogar
    else:
        executar_uma = acoes.acao_perguntar

    if pergunta:
        return executar_uma(servico, pergunta, k=argumentos.k)

    console.habilitar_historico()
    console.titulo("Modo conversa" + (" — busca" if modo == "buscar" else ""))
    console.detalhe("Uma pergunta por linha. Linha vazia encerra.")
    return acoes.acao_conversar(servico, executar_uma, k=argumentos.k)


def principal(argv: list[str] | None = None) -> int:
    """Ponto de entrada. Devolve o código de saída do processo."""
    parser = construir_parser()
    argumentos = parser.parse_args(argv)
    _normalizar_globais(argumentos)

    # A ordem importa: o arquivo entra primeiro, as flags por cima. Invertido,
    # `--colecao` seria silenciosamente sobrescrito pelo que está em disco.
    carregada = configuracao.carregar(argumentos.config, usar_arquivo=not argumentos.sem_config)
    config = carregada.config
    _aplicar_opcoes_globais(argumentos, config)
    servico = Servico(
        carregada=carregada,
        ao_decompor=acoes.mostrar_subconsultas,
        ao_ajustar_contexto=acoes.avisar_ajuste_de_contexto,
    )

    comando = argumentos.comando or "menu"

    if comando != "config":
        for aviso in carregada.avisos:
            console.aviso(aviso)

    try:
        if comando == "menu":
            return menu.executar(servico)
        if comando == "ambiente":
            return 0 if acoes.acao_ambiente(servico) else 1
        if comando == "baixar":
            return 0 if acoes.acao_baixar(servico, interativo=sys.stdin.isatty()) else 1
        if comando == "chunking":
            sucesso = acoes.acao_chunking(
                servico,
                interativo=sys.stdin.isatty(),
                arquivo_saida=argumentos.saida,
            )
            return 0 if sucesso else 1
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
        if comando == "avaliar" and argumentos.conversa:
            return (
                0
                if acoes.acao_avaliar_conversa(
                    servico,
                    k=argumentos.k,
                    caminho_dos_casos=Path(argumentos.casos) if argumentos.casos else None,
                )
                else 1
            )
        if comando == "avaliar":
            return (
                0
                if acoes.acao_avaliar(
                    servico,
                    k=argumentos.k,
                    comparar_configuracoes=argumentos.comparar,
                    caminho_dos_casos=Path(argumentos.casos) if argumentos.casos else None,
                )
                else 1
            )
        if comando == "acelerador":
            return (
                0
                if acoes.acao_acelerador(indice_apenas=argumentos.indice, arquitetura_apenas=argumentos.arquitetura)
                else 1
            )
        if comando == "marcos":
            return 0 if acoes.acao_listar_marcos(servico) else 1
        if comando == "config":
            if argumentos.caminho:
                console.info(str(carregada.caminho or configuracao.CAMINHO_PADRAO_DA_CONFIGURACAO))
                return 0
            acoes.acao_mostrar_config(servico)
            if argumentos.salvar:
                return 0 if acoes.acao_salvar_config(servico, argumentos.config) else 1
    except ErroPipeline as erro:
        console.erro_do_pipeline(erro)
        return 1
    except KeyboardInterrupt:
        console.aviso("\nInterrompido.")
        return 130

    return 0
