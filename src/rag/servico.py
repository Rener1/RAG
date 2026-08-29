"""
Composição das dependências (composition root).

Um lugar só onde as implementações concretas encontram os protocolos. As
etapas recebem o que precisam já pronto; nenhuma delas constrói cliente,
lê configuração global ou sabe que o banco é Qdrant.

Trocar uma peça — outro banco vetorial, outro provedor de embedding — é
mudar a linha correspondente aqui.
"""

from functools import cached_property
from pathlib import Path

from .clientes import ClienteOllama, ColetorUESP, GeradorOllama, RepositorioQdrant
from .config import CONFIG, Config
from .etapas import RelatorProgresso, sem_progresso
from .etapas import chunking as etapa_chunking
from .etapas import download as etapa_download
from .etapas import indexacao as etapa_indexacao
from .etapas.recuperacao import Recuperador
from .modelos import ResultadoEtapa
from .orquestrador import MotorRag


class Servico:
    """Fachada do pipeline: monta as peças e expõe as etapas como métodos.

    Os clientes são construídos sob demanda (`cached_property`) porque abrir
    conexão com Qdrant e Ollama para rodar só o chunking seria exigir serviços
    de pé sem necessidade nenhuma.
    """

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or CONFIG

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
    def recuperador(self) -> Recuperador:
        return Recuperador(self.embutidor, self.repositorio, self.config.busca)

    @cached_property
    def motor(self) -> MotorRag:
        return MotorRag(self.recuperador, self.gerador)

    # ── etapas ────────────────────────────────────────────────────────────

    def baixar_corpus(self, progresso: RelatorProgresso = sem_progresso) -> ResultadoEtapa:
        return etapa_download.executar(self.config.download, self.config.caminhos.corpus, self.coletor, progresso)

    def gerar_chunks(self, progresso: RelatorProgresso = sem_progresso) -> ResultadoEtapa:
        return etapa_chunking.executar(
            self.config.chunking,
            self.config.caminhos.corpus,
            self.config.caminhos.chunks,
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
