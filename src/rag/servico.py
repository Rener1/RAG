"""
Composição das dependências (composition root).

Um lugar só onde as implementações concretas encontram os protocolos. As
etapas recebem o que precisam já pronto; nenhuma delas constrói cliente,
lê configuração global ou sabe que o banco é Qdrant.

Trocar uma peça — outro banco vetorial, outro provedor de embedding — é
mudar a linha correspondente aqui.
"""

from collections.abc import Callable
from dataclasses import replace
from functools import cached_property
from pathlib import Path

from . import marco as marco_pedagogico
from .carga import EmbutidorLimitado, GeradorLimitado, LimitadorDeCarga, ReordenadorLimitado
from .clientes import ClienteOllama, ColetorUESP, GeradorOllama, ReordenadorLocal, RepositorioQdrant
from .config import CONFIG, Config, ConfiguracaoCarregada
from .etapas import RelatorProgresso, sem_progresso
from .etapas import chunking as etapa_chunking
from .etapas import download as etapa_download
from .etapas import indexacao as etapa_indexacao
from .etapas.geracao import montador_do_marco, montar_prompt
from .etapas.recuperacao import Recuperador
from .lexico import IndiceLexico, RecuperadorHibrido
from .marco import Marco
from .mediacao import ConsultaDecomposta, IntermediadorDeConsulta
from .modelos import ResultadoEtapa
from .orquestrador import MotorRag
from .protocolos import Embutidor, Gerador, RecuperadorDeTrechos, Reordenador
from .sessao import Dialogo


class Servico:
    """Fachada do pipeline: monta as peças e expõe as etapas como métodos.

    Os clientes são construídos sob demanda (`cached_property`) porque abrir
    conexão com Qdrant e Ollama para rodar só o chunking seria exigir serviços
    de pé sem necessidade nenhuma.
    """

    def __init__(
        self,
        config: Config | None = None,
        *,
        carregada: ConfiguracaoCarregada | None = None,
        ao_decompor: Callable[[ConsultaDecomposta], None] | None = None,
        ao_ajustar_contexto: Callable[[int, int], None] | None = None,
    ) -> None:
        # `carregada` traz de onde veio cada valor (padrão, arquivo ou flag);
        # quem constrói só com `config` — testes, sobretudo — não precisa saber.
        self.carregada = carregada or ConfiguracaoCarregada(config or CONFIG)
        self.config = self.carregada.config
        # A interface troca isto por uma função que imprime as sub-consultas.
        # Fica como atributo, e não como import, para o núcleo não conhecer o
        # console — mesma disciplina do relator de progresso das etapas.
        self.ao_decompor: Callable[[ConsultaDecomposta], None] = ao_decompor or (lambda consulta: None)
        self.ao_ajustar_contexto: Callable[[int, int], None] = ao_ajustar_contexto or (lambda recuperados, usados: None)

    # ── peças ─────────────────────────────────────────────────────────────

    @cached_property
    def limitador(self) -> LimitadorDeCarga | None:
        """Um só para o processo: é o que torna a fração global, e não por peça.

        `None` com `carga.fracao = 1` — sem limite, nada é embrulhado e o
        caminho é exatamente o de antes.
        """
        if self.config.carga.fracao == 1:
            return None
        return LimitadorDeCarga(self.config.carga.fracao)

    @cached_property
    def embutidor(self) -> Embutidor:
        cliente = ClienteOllama(self.config.embedding, self.config.carga.threads_de_cpu)
        return EmbutidorLimitado(cliente, self.limitador) if self.limitador else cliente

    @cached_property
    def repositorio(self) -> RepositorioQdrant:
        return RepositorioQdrant(self.config.vetorial)

    @cached_property
    def coletor(self) -> ColetorUESP:
        return ColetorUESP(self.config.download)

    @cached_property
    def gerador(self) -> GeradorOllama:
        return GeradorOllama(self.config.geracao, self.config.carga.threads_de_cpu)

    @cached_property
    def gerador_de_apoio(self) -> Gerador:
        """Gerador para as chamadas internas: triagem, reformulação, perguntas.

        Separado do `gerador` porque essas chamadas querem a resposta inteira e
        determinística, não texto saindo aos pedaços — e porque uma delas rodar
        com a temperatura da resposta final produziria sub-consulta criativa,
        que é exatamente o que não se quer numa busca.
        """
        gerador = GeradorOllama(
            replace(self.config.geracao, temperatura=0.0, streaming=False), self.config.carga.threads_de_cpu
        )
        # Limitado só este, e não o `gerador`: aqui são chamadas curtas e em
        # série (uma por caso na avaliação); a resposta final é uma rajada só.
        return GeradorLimitado(gerador, self.limitador) if self.limitador else gerador

    @cached_property
    def reordenador(self) -> Reordenador:
        """Cross-encoder que reordena os candidatos. Construído sob demanda."""
        reordenador = ReordenadorLocal(self.config.reordenacao)
        return ReordenadorLimitado(reordenador, self.limitador) if self.limitador else reordenador

    @cached_property
    def recuperador_base(self) -> Recuperador:
        """Busca vetorial direta, sem mediação. `buscar --sem-intermediar` usa esta."""
        # Com a mediação ligada, quem reordena é ela, depois de fundir — senão o
        # reordenador rodaria uma vez por sub-consulta, multiplicando o custo e
        # julgando contra a sub-consulta em vez de contra a pergunta original.
        reordena_aqui = self.config.busca.reordenar and not self.config.intermediacao.ligada
        return Recuperador(
            self.embutidor,
            self.repositorio,
            self.config.busca,
            reordenador=self.reordenador if reordena_aqui else None,
        )

    @cached_property
    def indice_lexico(self) -> IndiceLexico:
        """Índice BM25 sobre os chunks. Construído no primeiro uso, ~2 s."""
        return IndiceLexico(self.config.caminhos.chunks)

    @cached_property
    def recuperador_denso_ou_hibrido(self) -> RecuperadorDeTrechos:
        """A busca de base: densa, ou densa fundida com a léxica."""
        if not self.config.busca.hibrido:
            return self.recuperador_base
        return RecuperadorHibrido(self.recuperador_base, self.indice_lexico, self.config.busca)

    @cached_property
    def recuperador_com_mediacao(self) -> IntermediadorDeConsulta:
        """A camada de mediação, independente de estar ligada na configuração.

        `avaliar --comparar` precisa das duas configurações na mesma execução —
        é o único jeito de a comparação ser contra o mesmo índice e o mesmo
        gabarito, que é o que a torna legítima.
        """
        return IntermediadorDeConsulta(
            self.recuperador_denso_ou_hibrido,
            self.gerador_de_apoio,
            self.embutidor,
            self.config.intermediacao,
            self.config.busca,
            # Encaminha em vez de capturar: assim trocar `servico.ao_decompor`
            # depois da construção surte efeito. A avaliação silencia por aqui.
            ao_decompor=lambda consulta: self.ao_decompor(consulta),
            orientacao_do_marco=self.marco.secao("decomposicao") if self.marco else "",
            # O idioma é do acervo, não da máquina, então mora no marco e viaja
            # junto com `colecao_recomendada`. Trocar de corpus é trocar de marco.
            idioma_do_acervo=self.marco.metadado("idioma_do_acervo") if self.marco else "",
            reordenador=self.reordenador if self.config.busca.reordenar else None,
        )

    @cached_property
    def recuperador(self) -> RecuperadorDeTrechos:
        """O recuperador em vigor — com ou sem a camada de mediação.

        O tipo é o protocolo, e não a classe: é o que permite empilhar o
        intermediador aqui sem que nada acima saiba da diferença.
        """
        if self.config.intermediacao.ligada:
            return self.recuperador_com_mediacao
        return self.recuperador_denso_ou_hibrido

    @cached_property
    def marco(self) -> Marco | None:
        """O marco ativo, ou `None` quando `marco.ativo` está vazio.

        Marco quebrado levanta erro em vez de cair no prompt genérico: perder o
        marco em silêncio é perder exatamente o que separa este sistema de um
        chatbot com um prompt bonito.
        """
        if not self.config.marco.ativo:
            return None
        return marco_pedagogico.carregar(self.config.marco.ativo, self.config.caminhos.marcos)

    @property
    def orcamento_de_prompt(self) -> int:
        """Tokens que o prompt pode ocupar: a janela menos a reserva da resposta."""
        return max(0, self.config.geracao.num_ctx - self.config.geracao.reserva_para_resposta)

    @cached_property
    def motor(self) -> MotorRag:
        montador = montar_prompt if self.marco is None else montador_do_marco(self.marco)
        return MotorRag(
            self.recuperador,
            self.gerador,
            montador,
            orcamento_em_tokens=self.orcamento_de_prompt,
            ao_ajustar_contexto=self.ao_ajustar_contexto,
        )

    @cached_property
    def dialogo(self) -> Dialogo:
        return Dialogo(self.motor, self.gerador_de_apoio, self.config.sessao, self.marco)

    def recarregar_marco(self, identificador: str) -> Marco | None:
        """Troca o marco ativo nesta execução.

        A limpeza do cache não é detalhe: sem ela o `motor` já construído
        continuaria com o marco antigo, e a troca não teria efeito nenhum — sem
        erro, sem aviso, sem sintoma.
        """
        self.config.marco.ativo = identificador
        # O recuperador entra na lista porque a orientação de decomposição vem
        # do marco: sem invalidá-lo, a busca continuaria seguindo o marco antigo.
        for nome in ("marco", "motor", "recuperador", "recuperador_com_mediacao", "dialogo"):  # noqa: E501
            self.__dict__.pop(nome, None)
        return self.marco

    # ── etapas ────────────────────────────────────────────────────────────

    def baixar_corpus(self, progresso: RelatorProgresso = sem_progresso) -> ResultadoEtapa:
        return etapa_download.executar(self.config.download, self.config.caminhos.corpus, self.coletor, progresso)

    def gerar_chunks(
        self,
        progresso: RelatorProgresso = sem_progresso,
        arquivo_saida: Path | None = None,
    ) -> ResultadoEtapa:
        """Corta o corpus. `arquivo_saida` desvia o resultado do caminho padrão.

        O desvio existe para experimentar estratégia nova sem destruir o
        `chunks.jsonl` que corresponde ao índice já construído — sobrescrever esse
        arquivo por engano obriga a reindexar.
        """
        return etapa_chunking.executar(
            self.config.chunking,
            self.config.caminhos.corpus,
            arquivo_saida or self.config.caminhos.chunks,
            progresso,
        )

    def indexar(
        self,
        *,
        retomar: bool = True,
        recriar_colecao: bool = False,
        progresso: RelatorProgresso = sem_progresso,
    ) -> ResultadoEtapa:
        # Com a carga limitada, lote menor: a pausa vem depois de cada lote, e
        # lote menor é pausa mais fina — menos tempo em clock alto de uma vez.
        config_embedding = self.config.embedding
        if self.limitador:
            config_embedding = replace(config_embedding, tamanho_lote=self.config.carga.tamanho_lote)
        return etapa_indexacao.executar(
            config_embedding,
            self.embutidor,
            self.repositorio,
            self.config.caminhos.chunks,
            retomar=retomar,
            recriar_colecao=recriar_colecao,
            progresso=progresso,
        )

    # ── estado ────────────────────────────────────────────────────────────

    def contar_documentos(self) -> int:
        pasta: Path = self.config.caminhos.corpus
        return sum(1 for _ in pasta.glob("*.txt")) if pasta.is_dir() else 0

    def chunks_existem(self) -> bool:
        return self.config.caminhos.chunks.exists()
