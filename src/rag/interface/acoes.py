"""
Ações de alto nível — o que o programa faz, sem depender de como foi pedido.

Menu interativo e CLI chamam exatamente estas funções. É o que garante que as
duas portas de entrada tenham o mesmo comportamento: uma correção feita aqui
vale para as duas, e não existe funcionalidade que só o menu ou só a linha de
comando alcance.
"""

import time
from collections.abc import Iterator
from pathlib import Path

from .. import config as configuracao
from .. import marco as marco_pedagogico
from ..ambiente import Estado, pronto_para_perguntar, verificar
from ..erros import ErroPipeline
from ..etapas.geracao import validar_citacoes
from ..mediacao import ConsultaDecomposta
from ..modelos import EstadoDaSessao, ResultadoEtapa, TrechoRecuperado
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


def acao_chunking(servico: Servico, *, interativo: bool = True, arquivo_saida: Path | None = None) -> bool:
    """Etapa 2 — corta o corpus em trechos.

    `arquivo_saida` grava em outro lugar em vez do `chunks.jsonl` padrão. É o
    caminho para experimentar uma estratégia de corte sem destruir o artefato
    que corresponde ao índice já construído.
    """
    console.titulo("Etapa 2 — chunking")
    destino_padrao = arquivo_saida is None

    if interativo and destino_padrao and servico.chunks_existem():
        console.aviso(f"{servico.config.caminhos.chunks.name} já existe e será substituído.")
        if not console.confirmar("Refazer o chunking?", padrao=True):
            console.info("Cancelado.")
            return True

    console.detalhe(f"  Estratégia: {servico.config.chunking.estrategia}")
    if not destino_padrao:
        console.detalhe(f"  Saída desviada para {arquivo_saida} — {servico.config.caminhos.chunks.name} fica intacto.")

    progresso = console.Progresso("cortando")
    resultado = servico.gerar_chunks(progresso, arquivo_saida=arquivo_saida)
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

    if interativo and destino_padrao:
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


def mostrar_subconsultas(consulta: ConsultaDecomposta) -> None:
    """Imprime o que a mediação decidiu buscar.

    Mostrar isso não é enfeite: quando a resposta vem estranha, a primeira
    pergunta é se o sistema buscou o que se pediu — e sem isso na tela a
    reformulação seria uma caixa-preta entre a pergunta e o resultado.
    """
    if not consulta.houve_decomposicao:
        if consulta.motivo_do_fallback and consulta.motivo_do_fallback != "mediação desligada":
            console.detalhe(f"  busca direta — {consulta.motivo_do_fallback}")
        return

    console.info(f"\nBuscando {len(consulta.subconsultas)} consultas:")
    for subconsulta in consulta.subconsultas:
        # A primeira pode ser a consulta consolidada de uma sessão, que tem mais
        # de uma linha — sem colapsar, a listagem perde o alinhamento.
        numa_linha = " ".join(subconsulta.split())
        console.detalhe(f"  · {numa_linha[:110]}{'…' if len(numa_linha) > 110 else ''}")


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


def _apresentar_resposta(
    servico: Servico,
    trechos: list[TrechoRecuperado],
    fluxo: Iterator[str],
    inicio: float,
) -> bool:
    """Mostra as fontes, escreve a resposta conforme sai, e confere as citações.

    Extraído para ser o mesmo em `acao_perguntar` e `acao_dialogar`: as duas
    terminam igual, e duplicar o tratamento de interrupção e de erro de fluxo
    seria a forma mais fácil de as duas divergirem sem ninguém notar.
    """
    console.info(f"\nFontes recuperadas ({len(trechos)}):")
    _mostrar_trechos(trechos)

    console.secao("Resposta")
    escritor = console.EscritorFluido()
    pedacos: list[str] = []
    try:
        for pedaco in fluxo:
            pedacos.append(pedaco)
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

    invalidas = validar_citacoes("".join(pedacos), trechos)
    if invalidas:
        console.aviso(f"Citação sem trecho correspondente: {', '.join(dict.fromkeys(invalidas))}.")
        console.detalhe(
            "  → A resposta citou fonte que não está entre as recuperadas; trate a afirmação como não verificada."
        )

    console.detalhe(f"\n({time.monotonic() - inicio:.1f}s, modelo {servico.config.geracao.modelo})")
    return True


def acao_perguntar(servico: Servico, pergunta: str, k: int | None = None) -> bool:
    """Etapa 5 — ciclo RAG completo, com a resposta saindo conforme é gerada."""
    inicio = time.monotonic()
    try:
        _avisar_colecao_do_marco(servico)
        trechos, fluxo = servico.motor.responder_em_fluxo(pergunta, k=k)
    except ErroPipeline as erro:
        console.erro_do_pipeline(erro)
        return False

    if not trechos:
        console.aviso("Nenhum trecho recuperado — não há material para fundamentar uma resposta.")
        console.detalhe("  → Confira o diagnóstico do ambiente e se a coleção está indexada.")
        return False

    return _apresentar_resposta(servico, trechos, fluxo, inicio)


def acao_dialogar(servico: Servico, pergunta: str, k: int | None = None) -> bool:
    """Etapa 5 em modo dialógico — pode devolver perguntas antes de responder.

    Exige terminal: as perguntas devolvidas não têm para quem ir sem alguém do
    outro lado. Quem chama sem terminal usa `acao_perguntar`, e é a CLI que
    escolhe entre as duas.
    """
    inicio = time.monotonic()
    dialogo = servico.dialogo
    sessao = dialogo.iniciar(pergunta)

    try:
        _avisar_colecao_do_marco(servico)
        demanda = dialogo.classificar(sessao)

        if sessao.estado is EstadoDaSessao.PROBLEMATIZACAO:
            console.detalhe(f"  demanda: {demanda.value.replace('_', ' ')}")

        while sessao.estado is EstadoDaSessao.PROBLEMATIZACAO:
            perguntas = dialogo.problematizar(sessao)
            if not perguntas:
                break

            console.secao("Antes de responder")
            for numero, devolvida in enumerate(perguntas, start=1):
                console.info(f"  {numero}. {devolvida}")
            console.detalhe("\n  Responda o que puder numa linha só. Enter em branco segue para a busca.")

            resposta = console.perguntar("resposta")
            dialogo.receber(sessao, resposta)

        trechos, fluxo = dialogo.responder(sessao, k=k)
    except ErroPipeline as erro:
        console.erro_do_pipeline(erro)
        return False
    except KeyboardInterrupt:
        dialogo.encerrar(sessao)
        console.aviso("\nConversa encerrada.")
        return False

    if not trechos:
        console.aviso("Nenhum trecho recuperado — não há material para fundamentar uma resposta.")
        console.detalhe("  → Confira o diagnóstico do ambiente e se a coleção está indexada.")
        return False

    resultado = _apresentar_resposta(servico, trechos, fluxo, inicio)
    dialogo.encerrar(sessao)
    return resultado


# ── marco pedagógico ──────────────────────────────────────────────────────


def acao_listar_marcos(servico: Servico) -> bool:
    """Lista os marcos disponíveis, validando cada um.

    Valida em vez de só listar nomes porque um marco quebrado só apareceria na
    hora de perguntar, e a mensagem é mais útil aqui, ao lado dos que funcionam.
    """
    pasta = servico.config.caminhos.marcos
    console.titulo("Marcos pedagógicos")
    console.detalhe(f"  pasta: {pasta}")

    identificadores = marco_pedagogico.listar(pasta)
    if not identificadores:
        console.falha(f"Nenhum marco em {pasta}.")
        console.detalhe("  → O repositório traz 'generico' e 'freiriano'. Confira se a pasta existe.")
        return False

    ativo = servico.config.marco.ativo
    tudo_certo = True

    for identificador in identificadores:
        marca = f"{console.VERDE}→{console.NORMAL}" if identificador == ativo else " "
        try:
            marco = marco_pedagogico.carregar(identificador, pasta)
        except ErroPipeline as erro:
            tudo_certo = False
            console.info(f"  {marca}  {console.VERMELHO}{identificador}{console.NORMAL} — {erro.mensagem}")
            if erro.sugestao:
                console.detalhe(f"       {erro.sugestao}")
            continue

        console.info(f"  {marca}  {marco.resumo()}")
        console.detalhe(f"       {marco.nome}")

    if not ativo:
        console.aviso("Nenhum marco ativo — o sistema usa o prompt genérico.")
    console.detalhe("\n  Trocar nesta execução: --marco NOME. Para valer sempre: [marco] ativo no config.toml.")
    return tudo_certo


def acao_usar_marco(servico: Servico, identificador: str) -> bool:
    """Troca o marco ativo nesta execução."""
    try:
        marco = servico.recarregar_marco(identificador)
    except ErroPipeline as erro:
        console.erro_do_pipeline(erro)
        return False

    if marco is None:
        console.aviso("Marco desligado — o sistema volta ao prompt genérico.")
    else:
        console.sucesso(f"Marco ativo: {marco.resumo()}")
    console.detalhe("  Vale só para esta execução. `config --salvar` grava a escolha.")
    return True


def _avisar_colecao_do_marco(servico: Servico) -> None:
    """Avisa quando o marco foi escrito para outro acervo. Avisa, não bloqueia."""
    marco = servico.marco
    if marco is None:
        return

    recomendada = marco.metadados.get("colecao_recomendada", "")
    em_uso = servico.config.vetorial.colecao
    if recomendada and recomendada != em_uso:
        console.aviso(
            f"O marco '{marco.identificador}' foi escrito para a coleção '{recomendada}', e a busca usa '{em_uso}'."
        )


# ── configuração ──────────────────────────────────────────────────────────


def acao_mostrar_config(servico: Servico) -> None:
    """Mostra a configuração em vigor e a procedência de cada valor.

    A procedência é o que responde "por que aqui está diferente?" sem ninguém
    precisar abrir três arquivos: cada linha diz se o valor veio do padrão do
    código, do `config.toml` ou de uma flag desta execução.
    """
    carregada = servico.carregada
    config = carregada.config
    origens = configuracao.origem_dos_valores(carregada)

    console.titulo("Configuração atual")
    if carregada.caminho:
        console.detalhe(f"  arquivo: {carregada.caminho}")
    else:
        console.detalhe(f"  arquivo: nenhum (padrões do código; seria {configuracao.CAMINHO_PADRAO_DA_CONFIGURACAO})")

    for aviso in carregada.avisos:
        console.aviso(aviso)

    for nome_secao, secao in config.secoes().items():
        console.secao(nome_secao)
        for campo in config.campos_editaveis(nome_secao):
            origem = origens[(nome_secao, campo)]
            marca = "" if origem == "padrão" else f"  {console.APAGADO}({origem}){console.NORMAL}"
            console.info(f"  {campo:20} {getattr(secao, campo)}{marca}")

    console.detalhe("\nAlterações valem só para esta execução até serem gravadas com `config --salvar`.")


def acao_salvar_config(servico: Servico, caminho: Path | None = None) -> bool:
    """Grava em disco o que difere do padrão, incluindo o que veio de flags."""
    mudancas = configuracao.diferencas(servico.config)
    try:
        alvo = configuracao.salvar(servico.config, caminho)
    except OSError as erro:
        console.falha(f"Não foi possível gravar: {erro}")
        return False

    if not mudancas:
        console.sucesso(f"{alvo} gravado — vazio, porque nada difere dos padrões do código.")
        return True

    total = sum(len(campos) for campos in mudancas.values())
    console.sucesso(f"{total} valor(es) gravados em {alvo}.")
    for nome_secao, campos in mudancas.items():
        for campo, valor in campos.items():
            console.detalhe(f"  {nome_secao}.{campo} = {valor}")
    return True
