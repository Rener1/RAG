"""
Ações de alto nível — o que o programa faz, sem depender de como foi pedido.

Menu interativo e CLI chamam exatamente estas funções. É o que garante que as
duas portas de entrada tenham o mesmo comportamento: uma correção feita aqui
vale para as duas, e não existe funcionalidade que só o menu ou só a linha de
comando alcance.
"""

import time
from collections.abc import Callable, Iterator
from pathlib import Path

from .. import avaliacao
from .. import config as configuracao
from .. import marco as marco_pedagogico
from ..acelerador import arquiteturas_amd
from ..acelerador import detectar as detectar_acelerador
from ..ambiente import Estado, pronto_para_perguntar, verificar
from ..avaliacao import ResultadoDaAvaliacao
from ..conversa import Conversa
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


def _avisar_carga(servico: Servico) -> None:
    """Diz que a carga está limitada — senão o tempo maior parece defeito."""
    fracao = servico.config.carga.fracao
    if fracao < 1:
        console.detalhe(f"  Carga limitada a {fracao:.0%} do tempo (carga.fracao) — mais lento, mais frio.")


def _relatar_descanso(servico: Servico) -> None:
    limitador = servico.__dict__.get("limitador")
    if limitador and limitador.ocupado:
        console.detalhe(
            f"  Trabalho {limitador.ocupado:.0f} s, descanso {limitador.descansado:.0f} s "
            f"(limitador em {limitador.fracao:.0%})."
        )


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

    _avisar_carga(servico)
    try:
        progresso = console.Progresso("indexando")
        resultado = servico.indexar(retomar=retomar, recriar_colecao=recriar, progresso=progresso)
        progresso.encerrar()
    except ErroPipeline as erro:
        console.erro_do_pipeline(erro)
        return False

    _relatar(resultado, f"chunks indexados em '{resultado.detalhes['colecao']}'")
    console.detalhe(f"  Total na coleção agora: {servico.repositorio.contar_pontos()} pontos.")
    _relatar_descanso(servico)
    return not resultado.houve_falha


# ── consulta ──────────────────────────────────────────────────────────────


def avisar_ajuste_de_contexto(recuperados: int, usados: int) -> None:
    """Diz quando trechos foram descartados para o prompt caber na janela.

    Sem isto, quem pede `--k 12` e recebe 7 fontes não tem como saber se o
    acervo tinha só 7 ou se 5 foram cortadas — e são coisas bem diferentes.
    """
    console.aviso(
        f"{recuperados - usados} de {recuperados} trechos ficaram de fora: o prompt não caberia na janela do modelo."
    )
    console.detalhe("  → Para usar mais trechos, suba `geracao.num_ctx` (`python3 main.py config`).")


def mostrar_subconsultas(consulta: ConsultaDecomposta) -> None:
    """Imprime o que a mediação decidiu buscar.

    Mostrar isso não é enfeite: quando a resposta vem estranha, a primeira
    pergunta é se o sistema buscou o que se pediu — e sem isso na tela a
    reformulação seria uma caixa-preta entre a pergunta e o resultado.
    """
    if not consulta.houve_decomposicao:
        if consulta.descartadas_por_redundancia:
            console.detalhe(
                f"  busca direta — as {consulta.descartadas_por_redundancia} variações propostas "
                "traziam o mesmo material"
            )
        elif consulta.motivo_do_fallback and consulta.motivo_do_fallback != "mediação desligada":
            console.detalhe(f"  busca direta — {consulta.motivo_do_fallback}")
        return

    descartadas = (
        f" ({consulta.descartadas_por_redundancia} redundante(s) descartada(s))"
        if consulta.descartadas_por_redundancia
        else ""
    )
    console.info(f"\nBuscando {len(consulta.subconsultas)} consultas{descartadas}:")
    for subconsulta in consulta.subconsultas:
        # A primeira pode ser a consulta consolidada de uma sessão, que tem mais
        # de uma linha — sem colapsar, a listagem perde o alinhamento.
        numa_linha = " ".join(subconsulta.split())
        console.detalhe(f"  · {numa_linha[:110]}{'…' if len(numa_linha) > 110 else ''}")


def _mostrar_trechos(trechos: list[TrechoRecuperado]) -> None:
    for posicao, trecho in enumerate(trechos, start=1):
        console.info(f"  {posicao}. score={trecho.score:.3f}  [{trecho.titulo_pagina}]")
        console.detalhe(f"     {trecho.previa()}")


def _entender_na_conversa(conversa: Conversa | None, pergunta: str) -> str:
    """A pergunta como vai à busca — reescrita quando é seguimento.

    A reescrita aparece na tela pelo mesmo motivo das sub-consultas: quem
    pergunta precisa ver o que o sistema entendeu, e corrigir se entendeu errado.
    """
    if conversa is None:
        return pergunta
    reescrita = conversa.reescrever(pergunta)
    if reescrita.mudou:
        console.detalhe(f"  entendida como: {reescrita.consulta}")
    return reescrita.consulta


def acao_buscar(servico: Servico, pergunta: str, k: int | None = None, conversa: Conversa | None = None) -> bool:
    """Etapa 4 — só recuperação, sem gerar texto.

    Serve para avaliar a recuperação isoladamente: se o trecho certo não
    aparece aqui, o problema não está no prompt de geração.
    """
    inicio = time.monotonic()
    try:
        consulta = _entender_na_conversa(conversa, pergunta)
        trechos = servico.recuperador.buscar(consulta, k=k)
    except ErroPipeline as erro:
        console.erro_do_pipeline(erro)
        return False

    if not trechos:
        console.aviso("Nenhum trecho recuperado.")
        console.detalhe("  → Coleção vazia, ou `busca.score_minimo` alto demais.")
        return False

    console.info(f"\n{len(trechos)} trechos recuperados em {time.monotonic() - inicio:.1f}s:")
    _mostrar_trechos(trechos)
    if conversa is not None:
        conversa.registrar(pergunta, consulta)
    return True


def _apresentar_resposta(
    servico: Servico,
    trechos: list[TrechoRecuperado],
    fluxo: Iterator[str],
    inicio: float,
) -> str | None:
    """Mostra as fontes, escreve a resposta conforme sai, e confere as citações.

    Devolve o texto da resposta, ou `None` se ela não chegou ao fim — é o texto
    que a conversa guarda para a pergunta seguinte.

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
        return None
    except KeyboardInterrupt:
        escritor.encerrar()
        console.aviso("Geração interrompida.")
        return None

    invalidas = validar_citacoes("".join(pedacos), trechos)
    if invalidas:
        console.aviso(f"Citação sem trecho correspondente: {', '.join(dict.fromkeys(invalidas))}.")
        console.detalhe(
            "  → A resposta citou fonte que não está entre as recuperadas; trate a afirmação como não verificada."
        )

    console.detalhe(f"\n({time.monotonic() - inicio:.1f}s, modelo {servico.config.geracao.modelo})")
    return "".join(pedacos)


def _historico(conversa: Conversa | None) -> str:
    return conversa.historico_para_o_prompt() if conversa is not None else ""


def acao_perguntar(servico: Servico, pergunta: str, k: int | None = None, conversa: Conversa | None = None) -> bool:
    """Etapa 5 — ciclo RAG completo, com a resposta saindo conforme é gerada."""
    inicio = time.monotonic()
    try:
        _avisar_colecao_do_marco(servico)
        consulta = _entender_na_conversa(conversa, pergunta)
        trechos, fluxo = servico.motor.responder_em_fluxo(consulta, k=k, historico=_historico(conversa))
    except ErroPipeline as erro:
        console.erro_do_pipeline(erro)
        return False

    if not trechos:
        console.aviso("Nenhum trecho recuperado — não há material para fundamentar uma resposta.")
        console.detalhe("  → Confira o diagnóstico do ambiente e se a coleção está indexada.")
        return False

    resposta = _apresentar_resposta(servico, trechos, fluxo, inicio)
    if resposta is not None and conversa is not None:
        conversa.registrar(pergunta, consulta, resposta)
    return resposta is not None


def acao_dialogar(servico: Servico, pergunta: str, k: int | None = None, conversa: Conversa | None = None) -> bool:
    """Etapa 5 em modo dialógico — pode devolver perguntas antes de responder.

    Exige terminal: as perguntas devolvidas não têm para quem ir sem alguém do
    outro lado. Quem chama sem terminal usa `acao_perguntar`, e é a CLI que
    escolhe entre as duas.
    """
    inicio = time.monotonic()
    dialogo = servico.dialogo

    try:
        _avisar_colecao_do_marco(servico)
        consulta = _entender_na_conversa(conversa, pergunta)
        sessao = dialogo.iniciar(consulta)
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

        trechos, fluxo = dialogo.responder(sessao, k=k, historico=_historico(conversa))
    except ErroPipeline as erro:
        console.erro_do_pipeline(erro)
        return False
    except KeyboardInterrupt:
        console.aviso("\nConversa encerrada.")
        return False

    if not trechos:
        console.aviso("Nenhum trecho recuperado — não há material para fundamentar uma resposta.")
        console.detalhe("  → Confira o diagnóstico do ambiente e se a coleção está indexada.")
        return False

    resposta = _apresentar_resposta(servico, trechos, fluxo, inicio)
    dialogo.encerrar(sessao)
    if resposta is not None and conversa is not None:
        conversa.registrar(pergunta, consulta, resposta)
    return resposta is not None


# ── modo conversa ─────────────────────────────────────────────────────────

COMANDO_NOVA_CONVERSA = "/nova"

ExecutarUma = Callable[..., bool]


def acao_conversar(servico: Servico, executar_uma: ExecutarUma, k: int | None = None) -> bool:
    """Laço de perguntas com memória — o mesmo para a CLI e para o menu.

    Cada linha é uma pergunta; linha vazia encerra; `/nova` esquece o que foi
    dito e começa outra conversa. Com `conversa.ligada = false`, cada pergunta
    chega sozinha, como antes. A memória vive só neste laço: sair dele é
    esquecer.
    """
    conversa = servico.nova_conversa()
    if conversa is not None:
        console.detalhe(f"Com memória das últimas perguntas. '{COMANDO_NOVA_CONVERSA}' começa outra conversa.")

    while True:
        pergunta = console.perguntar("\npergunta")
        if not pergunta:
            # Sair da conversa é uso normal, não falha.
            return True
        if pergunta.strip().casefold() == COMANDO_NOVA_CONVERSA:
            conversa = servico.nova_conversa()
            console.info("Nova conversa — o que foi dito antes não conta mais.")
            continue
        executar_uma(servico, pergunta, k=k, conversa=conversa)


# ── avaliação ─────────────────────────────────────────────────────────────


def _linha_de_metricas(resultado: ResultadoDaAvaliacao) -> str:
    trechos = f"  trechos/caso={resultado.trechos_por_caso:.1f}" if resultado.k is None else ""
    # O corte do orçamento aparece sempre que medido, mesmo zerado: "0 cortes"
    # é a confirmação de que o recall acima é o que chega ao modelo.
    orcamento = ""
    if resultado.mediu_orcamento:
        orcamento = f"  cortes={resultado.casos_cortados}/{resultado.total}"
        if resultado.recall_no_prompt != resultado.recall:
            orcamento += f"  recall no prompt={resultado.recall_no_prompt:.0%}"
    return (
        f"recall{resultado.descricao_do_k}={resultado.recall:.0%}  "
        f"cobertura={resultado.cobertura_media:.0%}  "
        f"mrr={resultado.mrr:.3f}{trechos}{orcamento}  ({resultado.segundos:.1f}s)"
    )


def _mostrar_por_tipo(resultado: ResultadoDaAvaliacao) -> None:
    for tipo, (quantidade, recall) in resultado.por_tipo().items():
        console.detalhe(f"    {tipo:<16} {quantidade:>3} casos   recall={recall:.0%}")


def _k_da_avaliacao(servico: Servico, k: int | None) -> int | None:
    """O `k` que a avaliação mede e rotula. `None` = quantidade dinâmica.

    Com reordenação o `k` é fixo: o corte relativo pressupõe a lista ordenada
    por cosseno, e o cross-encoder ordena por outro critério. Rotular "k
    dinâmico" ali descreveria errado o que de fato rodou.
    """
    if k is not None:
        return k
    dinamico = servico.config.busca.limiar_relativo > 0 and not servico.config.busca.reordenar
    return None if dinamico else servico.config.busca.k


def acao_avaliar(
    servico: Servico,
    k: int | None = None,
    comparar_configuracoes: bool = False,
    caminho_dos_casos: Path | None = None,
) -> bool:
    """Mede a recuperação contra o gabarito. Não gera texto — só camada 1.

    A qualidade da resposta não é medida aqui de propósito: é rubrica humana
    (`docs/fase-3-avaliacao-e-servidor.md` §5), e métrica automática não pega o
    modo de falha que importa.
    """
    caminho = caminho_dos_casos or servico.config.caminhos.casos_de_avaliacao
    # `None` entrega a decisão à política de busca — é assim que o `k` dinâmico
    # fica mensurável. Com `--k N`, o número pedido vale, que é o que a varredura
    # de `k` precisa para ser comparável.
    #
    # Com reordenação o `k` volta a ser fixo: o corte relativo pressupõe a lista
    # ordenada por cosseno, e o cross-encoder ordena por outro critério. Dizer
    # "k dinâmico" ali seria rotular errado o que de fato aconteceu.
    k_efetivo = _k_da_avaliacao(servico, k)

    try:
        casos = avaliacao.carregar_casos(caminho)
    except ErroPipeline as erro:
        console.erro_do_pipeline(erro)
        return False

    console.titulo("Avaliação da recuperação")
    if k_efetivo is None:
        descricao = (
            f"k dinâmico (>= {servico.config.busca.limiar_relativo:.2f} do topo, "
            f"entre {servico.config.busca.k_minimo} e {servico.config.busca.k_maximo})"
        )
    elif servico.config.busca.reordenar:
        descricao = f"k={k_efetivo}, reordenando {servico.config.busca.candidatos_para_reordenar} candidatos"
    else:
        descricao = f"k={k_efetivo}"
    console.detalhe(f"{len(casos)} casos de {caminho.name}, {descricao}")
    _avisar_carga(servico)

    # Quarenta decomposições impressas afogariam o resultado, que é o que
    # interessa aqui. A barra de progresso já diz que algo está acontecendo.
    relator_anterior = servico.ao_decompor
    servico.ao_decompor = lambda consulta: None

    def medir(recuperador, rotulo: str):
        progresso = console.Progresso(rotulo)
        try:
            return avaliacao.avaliar(
                casos, recuperador, k_efetivo, rotulo, progresso=progresso, ajustar=servico.motor.trechos_que_cabem
            )
        finally:
            progresso.encerrar()

    try:
        if not comparar_configuracoes:
            resultado = medir(servico.recuperador, "avaliando")
            console.secao("Resultado")
            console.info(f"  {_linha_de_metricas(resultado)}")
            _mostrar_por_tipo(resultado)
            return True

        base = medir(servico.recuperador_base, "busca direta")
        mediada = medir(servico.recuperador_com_mediacao, "com mediação")
    except ErroPipeline as erro:
        console.erro_do_pipeline(erro)
        return False
    finally:
        servico.ao_decompor = relator_anterior

    console.secao("Comparação")
    console.info(f"  busca direta   {_linha_de_metricas(base)}")
    _mostrar_por_tipo(base)
    console.info(f"\n  com mediação   {_linha_de_metricas(mediada)}")
    _mostrar_por_tipo(mediada)

    delta = mediada.recall - base.recall
    veredito = "mediação à frente" if delta > 0 else ("empate" if delta == 0 else "busca direta à frente")
    console.info(f"\n  diferença de recall: {delta:+.1%} — {veredito}")

    mudancas = avaliacao.comparar(base, mediada)
    if mudancas:
        console.secao("Casos que mudaram de posição")
        for caso, antes, depois in mudancas[:12]:
            console.detalhe(f"  {caso.identificador:<9} {_posicao(antes)} -> {_posicao(depois)}   {caso.demanda[:52]}")
        if len(mudancas) > 12:
            console.detalhe(f"  ... e mais {len(mudancas) - 12}")
    else:
        console.detalhe("\n  Nenhum caso mudou de posição.")

    return True


def acao_avaliar_conversa(servico: Servico, k: int | None = None, caminho_dos_casos: Path | None = None) -> bool:
    """Mede a memória de conversa: o seguimento cru contra o reescrito.

    Mesmo recuperador, mesmo índice, mesmo gabarito; muda só o que vai à busca.
    Não gera resposta — a reescrita chama o modelo, como a mediação já chama,
    mas a métrica continua sendo de recuperação.
    """
    caminho = caminho_dos_casos or servico.config.caminhos.casos_de_conversa
    try:
        casos = avaliacao.carregar_casos(caminho)
    except ErroPipeline as erro:
        console.erro_do_pipeline(erro)
        return False

    console.titulo("Avaliação da memória de conversa")
    seguimentos = sum(1 for caso in casos if caso.historico)
    console.detalhe(f"{len(casos)} casos de {caminho.name}, {seguimentos} com histórico")
    _avisar_carga(servico)

    k = _k_da_avaliacao(servico, k)

    def reescrever(historico: tuple[str, ...], pergunta: str) -> str:
        conversa = Conversa.com_perguntas_anteriores(servico.gerador_de_apoio, servico.config.conversa, list(historico))
        return conversa.reescrever(pergunta).consulta

    relator_anterior = servico.ao_decompor
    servico.ao_decompor = lambda consulta: None

    def medir(rotulo: str, funcao):
        progresso = console.Progresso(rotulo)
        try:
            return avaliacao.avaliar(
                casos,
                servico.recuperador,
                k,
                rotulo,
                progresso=progresso,
                ajustar=servico.motor.trechos_que_cabem,
                reescrever=funcao,
            )
        finally:
            progresso.encerrar()

    try:
        cru = medir("seguimento cru", None)
        reescrito = medir("reescrito", reescrever)
    except ErroPipeline as erro:
        console.erro_do_pipeline(erro)
        return False
    finally:
        servico.ao_decompor = relator_anterior

    console.secao("Comparação")
    console.info(f"  seguimento cru   {_linha_de_metricas(cru)}")
    console.info(f"  reescrito        {_linha_de_metricas(reescrito)}")
    console.info(f"\n  diferença de recall: {reescrito.recall - cru.recall:+.1%}")

    console.secao("O que foi à busca")
    antes = cru.por_identificador()
    for resultado in reescrito.resultados:
        caso = resultado.caso
        if not caso.historico:
            continue
        posicoes = f"{_posicao(antes[caso.identificador].posicao_do_primeiro_acerto)} -> {_posicao(resultado.posicao_do_primeiro_acerto)}"
        console.info(f"  {caso.identificador:<9} {posicoes:<22} {caso.demanda[:40]}")
        console.detalhe(f"            → {resultado.consulta or '(intacta)'}")
    return True


def _posicao(valor: int | None) -> str:
    return "não achou" if valor is None else f"#{valor}"


def acao_acelerador(indice_apenas: bool = False, arquitetura_apenas: bool = False) -> bool:
    """Diz qual build de `torch` esta máquina precisa.

    Existe como comando porque a resposta é necessária **antes** de qualquer
    instalação — na hora de construir a imagem — e porque errar custa o download
    inteiro: o wheel do acelerador errado instala sem reclamar e cai para CPU em
    silêncio.
    """
    acelerador = detectar_acelerador()

    if indice_apenas:
        # Saída limpa, para `--build-arg TORCH_INDEX=$(...)`.
        print(acelerador.indice_torch)
        return True

    if arquitetura_apenas:
        # Idem, para `GPU_ARCH`: descarta os kernels das outras arquiteturas na
        # imagem. Vazio quando não há GPU, e aí o build mantém todos.
        arquiteturas = arquiteturas_amd()
        print(arquiteturas[0] if arquiteturas else "")
        return True

    console.titulo("Acelerador desta máquina")
    console.info(f"  detectado: {acelerador.detalhe}")
    console.info(f"  tipo:      {acelerador.tipo}")
    console.info(f"  índice:    {acelerador.indice_torch}")
    if acelerador.aviso:
        console.aviso(acelerador.aviso)

    if acelerador.acelerado:
        console.detalhe("\n  Para construir a imagem com reordenação acelerada:")
        console.detalhe("    podman compose --profile gpu build rag-gpu")
    else:
        console.detalhe("\n  Sem acelerador, a reordenação roda em CPU e custa segundos por consulta.")
        console.detalhe("  O restante do pipeline não depende dela.")

    return True


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


def _campo_inerte(config, nome_secao: str, campo: str) -> str:
    """Marca campo que está na configuração mas não tem efeito no estado atual.

    Existe por causa de um par específico: com `limiar_relativo` ligado, a
    quantidade de trechos é decidida por ele e `k` deixa de valer. Sem esta
    marca, quem ajustasse `k` esperando efeito não teria como descobrir por quê.
    """
    if nome_secao == "busca" and campo == "k" and config.busca.limiar_relativo > 0 and not config.busca.reordenar:
        return f"  {console.APAGADO}(sem efeito: limiar_relativo decide a quantidade){console.NORMAL}"
    if nome_secao == "busca" and campo == "limiar_relativo" and config.busca.reordenar:
        return f"  {console.APAGADO}(sem efeito: com reordenação, `k` decide){console.NORMAL}"
    return ""


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
            inerte = _campo_inerte(config, nome_secao, campo)
            console.info(f"  {campo:20} {getattr(secao, campo)}{marca}{inerte}")

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
