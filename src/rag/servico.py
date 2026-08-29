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
from .clientes import ClienteOllama, ColetorUESP, GeradorOllama, RepositorioQdrant
from .config import CONFIG, Config, ConfiguracaoCarregada
from .etapas import RelatorProgresso, sem_progresso
from .etapas import chunking as etapa_chunking
from .etapas import download as etapa_download
from .etapas import indexacao as etapa_indexacao
from .etapas.geracao import montador_do_marco
from .etapas.recuperacao import Recuperador
from .marco import Marco
from .mediacao import ConsultaDecomposta, IntermediadorDeConsulta
from .modelos import ResultadoEtapa
from .orquestrador import MotorRag
from .protocolos import RecuperadorDeTrechos
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
    ) -> None:
        # `carregada` traz de onde veio cada valor (padrão, arquivo ou flag);
        # quem constrói só com `config` — testes, sobretudo — não precisa saber.
        self.carregada = carregada or ConfiguracaoCarregada(config or CONFIG)
        self.config = self.carregada.config
        # A interface troca isto por uma função que imprime as sub-consultas.
        # Fica como atributo, e não como import, para o núcleo não conhecer o
        # console — mesma disciplina do relator de progresso das etapas.
        self.ao_decompor: Callable[[ConsultaDecomposta], None] = ao_decompor or (lambda consulta: None)

    # ── peças ─────────────────────────────────────────────────────────────

    @cached_property
    def embutidor(self) -> ClienteOllama:
        return ClienteOllama(self.config.embedding)

    @cached_property
    def repositorio(self) -> RepositorioQdrant:
        return RepositorioQdrant(self.config.vetorial)

    @cached_property
    def coletor(self) -> ColetorUESP:
        return ColetorUESP(self.config.download)

    @cached_property
    def gerador(self) -> GeradorOllama:
        return GeradorOllama(self.config.geracao)

    @cached_property
    def gerador_de_apoio(self) -> GeradorOllama:
        """Gerador para as chamadas internas: triagem, reformulação, perguntas.

        Separado do `gerador` porque essas chamadas querem a resposta inteira e
        determinística, não texto saindo aos pedaços — e porque uma delas rodar
        com a temperatura da resposta final produziria sub-consulta criativa,
        que é exatamente o que não se quer numa busca.
        """
        return GeradorOllama(replace(self.config.geracao, temperatura=0.0, streaming=False))

    @cached_property
    def recuperador_base(self) -> Recuperador:
        """Busca vetorial direta, sem mediação. `buscar --sem-intermediar` usa esta."""
        return Recuperador(self.embutidor, self.repositorio, self.config.busca)

    @cached_property
    def recuperador(self) -> RecuperadorDeTrechos:
        """O recuperador em vigor — com ou sem a camada de mediação.

        O tipo é o protocolo, e não a classe: é o que permite empilhar o
        intermediador aqui sem que nada acima saiba da diferença.
        """
        if not self.config.intermediacao.ligada:
            return self.recuperador_base

        return IntermediadorDeConsulta(
            self.recuperador_base,
            self.gerador_de_apoio,
            self.config.intermediacao,
            self.config.busca,
            ao_decompor=self.ao_decompor,
            orientacao_do_marco=self.marco.secao("decomposicao") if self.marco else "",
        )

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

    @cached_property
    def motor(self) -> MotorRag:
        if self.marco is None:
            return MotorRag(self.recuperador, self.gerador)
        return MotorRag(self.recuperador, self.gerador, montador_do_marco(self.marco))

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
        for nome in ("marco", "motor", "recuperador", "dialogo"):
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
        `chunks.jsonl` que corresponde ao índice já construído — reindexar custa
        horas, e sobrescrever esse arquivo por engano é irreversível.
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
        return etapa_indexacao.executar(
            self.config.embedding,
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
