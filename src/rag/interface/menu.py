"""
Menu interativo — a porta de entrada padrão do programa.

O laço é sempre o mesmo: mostrar o estado atual, receber uma escolha, executar,
e devolver o controle ao usuário. Nada aqui encerra o programa por conta
própria: erro de etapa é relatado e o menu volta, porque o usuário quase sempre
quer corrigir e tentar de novo, não recomeçar do terminal.

Os modos de consulta (busca e pergunta) são laços próprios, onde o usuário
digita as perguntas que quiser e sai com uma linha vazia.
"""

from collections.abc import Callable
from dataclasses import dataclass

from ..config import Config
from ..erros import ErroPipeline
from ..servico import Servico
from . import acoes, console


@dataclass
class Opcao:
    """Uma linha do menu."""

    tecla: str
    rotulo: str
    acao: Callable[[], None]
    descricao: str = ""


def _cabecalho() -> None:
    console.info()
    console.info(f"{console.NEGRITO}IA Freiriana — pipeline RAG local{console.NORMAL}")
    console.detalhe("Protótipo da Fase 2 · corpus de teste UESP · tudo roda na máquina local")


def _linha_de_estado(servico: Servico) -> None:
    """Resumo do estado do pipeline, para o usuário saber o que já existe.

    Só leitura barata: contagem de arquivos e uma consulta ao banco. Se o banco
    estiver fora do ar, mostra isso em vez de estourar — o menu precisa abrir
    mesmo com serviço parado, senão não dá nem para chegar no diagnóstico.
    """
    documentos = servico.contar_documentos()
    chunks = "sim" if servico.chunks_existem() else "não"
    try:
        pontos = f"{servico.repositorio.contar_pontos()} pontos"
    except ErroPipeline:
        pontos = "indisponível"

    console.detalhe(
        f"corpus: {documentos} arquivos · chunks: {chunks} · coleção '{servico.config.vetorial.colecao}': {pontos}"
    )


def _laco_de_consulta(servico: Servico, modo: str) -> None:
    """Laço onde o usuário digita perguntas livremente.

    `modo` decide o que acontece com a pergunta: 'buscar' só recupera trechos,
    'perguntar' fecha o ciclo RAG completo.
    """
    e_busca = modo == "buscar"
    console.titulo("Busca — só recuperação" if e_busca else "Perguntar — ciclo RAG completo")
    console.detalhe(
        "Digite a pergunta e Enter. Linha vazia volta ao menu." + ("" if e_busca else "  Ctrl+C interrompe a geração.")
    )
    console.detalhe(f"k = {servico.config.busca.k} trechos por pergunta.")

    while True:
        pergunta = console.perguntar("\npergunta")
        if not pergunta:
            return
        if e_busca:
            acoes.acao_buscar(servico, pergunta)
        else:
            acoes.acao_perguntar(servico, pergunta)


def _editar_configuracao(config: Config) -> None:
    """Edita um campo de configuração para esta execução.

    Os campos vêm por introspecção das dataclasses, então campo novo aparece
    aqui sozinho, sem formulário para manter.
    """
    acoes.acao_mostrar_config(config)

    secao = console.perguntar("\nSeção (Enter volta)")
    if not secao:
        return
    if secao not in config.secoes():
        console.falha(f"Seção desconhecida. Disponíveis: {', '.join(config.secoes())}")
        return

    campos = config.campos_editaveis(secao)
    campo = console.perguntar(f"Campo ({', '.join(campos)})")
    if not campo:
        return
    if campo not in campos:
        console.falha(f"Campo desconhecido em '{secao}'.")
        return

    atual = getattr(config.secoes()[secao], campo)
    valor = console.perguntar(f"Novo valor para {secao}.{campo}", padrao=str(atual))
    try:
        novo = config.definir(secao, campo, valor)
    except (ValueError, TypeError) as erro:
        console.falha(f"Valor inválido: {erro}")
        return

    console.sucesso(f"{secao}.{campo} = {novo}")
    if secao in {"embedding", "vetorial", "geracao"}:
        console.aviso("Reinicie o programa para que clientes já abertos usem o valor novo.")


def executar(servico: Servico) -> int:
    """Laço principal do menu. Devolve o código de saída do processo."""
    console.habilitar_historico()

    opcoes = [
        Opcao("1", "Verificar ambiente", lambda: acoes.acao_ambiente(servico), "diagnóstico de serviços e artefatos"),
        Opcao("2", "Baixar corpus", lambda: acoes.acao_baixar(servico), "etapa 1 — rede, demorado"),
        Opcao("3", "Gerar chunks", lambda: acoes.acao_chunking(servico), "etapa 2 — rápido"),
        Opcao("4", "Indexar", lambda: acoes.acao_indexar(servico), "etapa 3 — embedding, muito demorado"),
        Opcao("5", "Buscar", lambda: _laco_de_consulta(servico, "buscar"), "etapa 4 — só recuperação"),
        Opcao("6", "Perguntar", lambda: _laco_de_consulta(servico, "perguntar"), "etapa 5 — resposta completa"),
        Opcao("7", "Configuração", lambda: _editar_configuracao(servico.config), "ver e ajustar parâmetros"),
    ]
    por_tecla = {opcao.tecla: opcao for opcao in opcoes}

    _cabecalho()

    while True:
        # Régua antes do menu: sem ela, a saída da ação anterior encosta nas
        # opções e o usuário perde de vista onde uma coisa termina e a outra começa.
        console.info(f"\n{console.APAGADO}{'─' * console.largura_util()}{console.NORMAL}")
        _linha_de_estado(servico)
        console.info()
        for opcao in opcoes:
            console.info(
                f"  {console.NEGRITO}{opcao.tecla}{console.NORMAL}  {opcao.rotulo:20} {console.APAGADO}{opcao.descricao}{console.NORMAL}"
            )
        console.info(f"  {console.NEGRITO}0{console.NORMAL}  {'Sair':20}")

        escolha = console.perguntar("\nopção")

        if escolha in {"0", "sair", "q"} or not escolha:
            console.info("Até logo.")
            return 0

        opcao = por_tecla.get(escolha)
        if not opcao:
            console.falha(f"Opção inválida: {escolha!r}")
            continue

        try:
            opcao.acao()
        except ErroPipeline as erro:
            # Erro esperado (serviço fora do ar, pré-requisito faltando): a
            # mensagem já explica o conserto, e o menu segue.
            console.erro_do_pipeline(erro)
        except KeyboardInterrupt:
            console.aviso("\nInterrompido — voltando ao menu.")
