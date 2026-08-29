"""
Ações de alto nível — o que o programa faz, sem depender de como foi pedido.

Menu interativo e CLI chamam exatamente estas funções. É o que garante que as
duas portas de entrada tenham o mesmo comportamento: uma correção feita aqui
vale para as duas, e não existe funcionalidade que só o menu ou só a linha de
comando alcance.
"""

import time

from ..ambiente import Estado, pronto_para_perguntar, verificar
from ..config import Config
from ..erros import ErroPipeline
from ..modelos import ResultadoEtapa, TrechoRecuperado
from ..servico import Servico
from . import console

# ── diagnóstico ───────────────────────────────────────────────────────────


def acao_ambiente(servico: Servico) -> bool:
    """Mostra o diagnóstico. Devolve se está tudo pronto para perguntar."""
    console.titulo("Diagnóstico do ambiente")
    itens = verificar(servico.config)

    for item in itens:
        linha = f"{item.nome}: {item.detalhe}"
        if item.estado is Estado.OK:
            console.sucesso(linha)
        elif item.estado is Estado.AVISO:
            console.aviso(linha)
        else:
            console.falha(linha)
        if item.sugestao:
            console.detalhe(f"  → {item.sugestao}")

    return pronto_para_perguntar(itens)


# ── etapas ────────────────────────────────────────────────────────────────


def _relatar(resultado: ResultadoEtapa, unidade: str) -> None:
    console.sucesso(f"{resultado.processados} {unidade}.")
    if resultado.ignorados:
        console.detalhe(f"  {resultado.ignorados} ignorados (já existiam ou foram descartados).")
    if resultado.houve_falha:
        console.aviso(f"{len(resultado.falhas)} lote(s) falharam — repetir a etapa recupera o que faltou.")
        for mensagem in resultado.falhas[:3]:
            console.detalhe(f"  {mensagem}")
        if len(resultado.falhas) > 3:
            console.detalhe(f"  ... e mais {len(resultado.falhas) - 3}")


def acao_baixar(servico: Servico, *, interativo: bool = True) -> bool:
    """Etapa 1 — baixa o corpus. Cara em rede: confirma antes, quando interativo."""
    console.titulo("Etapa 1 — download do corpus")
    ja_baixados = servico.contar_documentos()

    if ja_baixados:
        console.aviso(f"{ja_baixados} arquivos já existem em {servico.config.caminhos.corpus}.")
        console.detalhe("  O download pula o que já está em disco; só o que falta será buscado.")

    if interativo:
        console.detalhe("  São milhares de requisições à UESP. Pode levar bastante tempo.")
        if not console.confirmar("Continuar com o download?", padrao=not ja_baixados):
            console.info("Cancelado.")
            return True  # cancelar por escolha do usuário não é falha

    progresso = console.Progresso("baixando")
    resultado = servico.baixar_corpus(progresso)
    progresso.encerrar()
    _relatar(resultado, "páginas salvas")
    console.detalhe(f"  Encontradas {resultado.detalhes.get('titulos_encontrados', 0)} páginas no namespace.")
    return not resultado.houve_falha


def acao_chunking(servico: Servico, *, interativo: bool = True) -> bool:
    """Etapa 2 — corta o corpus em trechos."""
    console.titulo("Etapa 2 — chunking")

    if interativo and servico.chunks_existem():
        console.aviso(f"{servico.config.caminhos.chunks.name} já existe e será substituído.")
        if not console.confirmar("Refazer o chunking?", padrao=True):
            console.info("Cancelado.")
            return True

    console.detalhe(f"  Estratégia: {servico.config.chunking.estrategia}")
    progresso = console.Progresso("cortando")
    resultado = servico.gerar_chunks(progresso)
    progresso.encerrar()

    detalhes = resultado.detalhes
    _relatar(resultado, "chunks gerados")
    console.detalhe(f"  {detalhes['documentos']} documentos processados.")
    console.detalhe(
        f"  Tamanho — mín {detalhes['tamanho_minimo']}, médio {detalhes['tamanho_medio']}, "
        f"máx {detalhes['tamanho_maximo']} caracteres."
    )

    gigantes = detalhes["documentos_com_paragrafo_gigante"]
    if gigantes:
        console.detalhe(f"  {len(gigantes)} documento(s) tinham parágrafo acima do teto e foram subdivididos.")
    console.detalhe(f"  Salvo em {detalhes['arquivo']}")

    if interativo:
        console.aviso("O índice existente ficou defasado em relação a estes chunks — reindexe quando puder.")
    return not resultado.houve_falha


def acao_indexar(servico: Servico, *, interativo: bool = True, recriar: bool = False, retomar: bool = True) -> bool:
    """Etapa 3 — embedding e indexação. A mais cara do pipeline."""
    console.titulo("Etapa 3 — embedding e indexação")

    if not servico.chunks_existem():
        console.falha(f"{servico.config.caminhos.chunks} não existe.")
        console.detalhe("  → Rode a etapa de chunking antes desta.")
        return False

    pontos = servico.repositorio.contar_pontos()
    if pontos:
        console.info(f"A coleção '{servico.config.vetorial.colecao}' já tem {pontos} pontos.")

    if interativo:
        if pontos and not recriar:
            console.detalhe("  Por padrão, chunks já indexados são pulados (retomada).")
            recriar = console.confirmar("Apagar a coleção e indexar do zero?", padrao=False)
        console.detalhe("  Embedding local do corpus inteiro leva horas.")
        if not console.confirmar("Continuar com a indexação?", padrao=True):
            console.info("Cancelado.")
            return True

    try:
        progresso = console.Progresso("indexando")
        resultado = servico.indexar(retomar=retomar, recriar_colecao=recriar, progresso=progresso)
        progresso.encerrar()
    except ErroPipeline as erro:
        console.erro_do_pipeline(erro)
        return False

    _relatar(resultado, f"chunks indexados em '{resultado.detalhes['colecao']}'")
    console.detalhe(f"  Total na coleção agora: {servico.repositorio.contar_pontos()} pontos.")
    return not resultado.houve_falha


# ── consulta ──────────────────────────────────────────────────────────────


def _mostrar_trechos(trechos: list[TrechoRecuperado]) -> None:
    for posicao, trecho in enumerate(trechos, start=1):
        console.info(f"  {posicao}. score={trecho.score:.3f}  [{trecho.titulo_pagina}]")
        console.detalhe(f"     {trecho.previa()}")


def acao_buscar(servico: Servico, pergunta: str, k: int | None = None) -> bool:
    """Etapa 4 — só recuperação, sem gerar texto.

    Serve para avaliar a recuperação isoladamente: se o trecho certo não
    aparece aqui, o problema não está no prompt de geração.
    """
    inicio = time.monotonic()
    try:
        trechos = servico.recuperador.buscar(pergunta, k=k)
    except ErroPipeline as erro:
        console.erro_do_pipeline(erro)
        return False

    if not trechos:
        console.aviso("Nenhum trecho recuperado.")
        console.detalhe("  → Coleção vazia, ou `busca.score_minimo` alto demais.")
        return False

    console.info(f"\n{len(trechos)} trechos recuperados em {time.monotonic() - inicio:.1f}s:")
    _mostrar_trechos(trechos)
    return True


def acao_perguntar(servico: Servico, pergunta: str, k: int | None = None) -> bool:
    """Etapa 5 — ciclo RAG completo, com a resposta saindo conforme é gerada."""
    inicio = time.monotonic()
    try:
        trechos, fluxo = servico.motor.responder_em_fluxo(pergunta, k=k)
    except ErroPipeline as erro:
        console.erro_do_pipeline(erro)
        return False

    if not trechos:
        console.aviso("Nenhum trecho recuperado — não há material para fundamentar uma resposta.")
        console.detalhe("  → Confira o diagnóstico do ambiente e se a coleção está indexada.")
        return False

    console.info(f"\nFontes recuperadas ({len(trechos)}):")
    _mostrar_trechos(trechos)

    console.secao("Resposta")
    escritor = console.EscritorFluido()
    try:
        for pedaco in fluxo:
            escritor.escrever(pedaco)
        escritor.encerrar()
    except ErroPipeline as erro:
        escritor.encerrar()
        console.erro_do_pipeline(erro)
        return False
    except KeyboardInterrupt:
        escritor.encerrar()
        console.aviso("Geração interrompida.")
        return False

    console.detalhe(f"\n({time.monotonic() - inicio:.1f}s, modelo {servico.config.geracao.modelo})")
    return True


# ── configuração ──────────────────────────────────────────────────────────


def acao_mostrar_config(config: Config) -> None:
    console.titulo("Configuração atual")
    for nome_secao, secao in config.secoes().items():
        console.secao(nome_secao)
        for campo in config.campos_editaveis(nome_secao):
            console.info(f"  {campo:20} {getattr(secao, campo)}")
    console.detalhe("\nAlterações valem só para esta execução — os padrões ficam em src/rag/config.py.")
