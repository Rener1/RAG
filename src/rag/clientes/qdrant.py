"""
Repositório vetorial sobre o Qdrant.

Cumpre o protocolo `RepositorioVetorial`. Toda menção ao Qdrant no projeto
mora neste arquivo — as etapas conhecem só o protocolo, então trocar de banco
é escrever outra classe equivalente e injetá-la.
"""

import uuid

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from ..config import ConfigVetorial
from ..erros import ErroConexao, ErroDimensaoIncompativel, ErroPipeline, ErroPreRequisito
from ..modelos import Chunk, TrechoRecuperado

# Namespace fixo para os IDs. Precisa ser estável entre execuções: é o que faz
# reindexar sobrescrever o ponto existente em vez de criar um duplicado.
NAMESPACE_CHUNKS = uuid.NAMESPACE_DNS


def id_do_chunk(chunk_id: str) -> str:
    """UUID determinístico a partir do `chunk_id` legível.

    O Qdrant só aceita UUID ou inteiro como identificador, mas o `chunk_id`
    ("documento.txt::3") é o que faz sentido pra humano — então derivamos um
    do outro em vez de guardar um contador.
    """
    return str(uuid.uuid5(NAMESPACE_CHUNKS, chunk_id))


class RepositorioQdrant:
    """Acesso ao Qdrant, com as verificações que faltavam no script original."""

    def __init__(self, config: ConfigVetorial) -> None:
        self._config = config
        self._cliente = QdrantClient(url=config.url, timeout=config.timeout)

    @property
    def colecao(self) -> str:
        return self._config.colecao

    # ── inspeção ──────────────────────────────────────────────────────────

    def esta_disponivel(self) -> tuple[bool, str]:
        """Diagnóstico: (disponível, detalhe legível). Nunca levanta exceção."""
        try:
            colecoes = [c.name for c in self._cliente.get_collections().collections]
        except Exception as erro:  # o cliente encapsula erros de rede em tipos próprios
            return False, str(erro)
        return True, ", ".join(colecoes) if colecoes else "nenhuma coleção"

    def colecao_existe(self) -> bool:
        try:
            return self._cliente.collection_exists(self._config.colecao)
        except Exception as erro:
            raise self._erro_conexao(erro) from erro

    def dimensao_da_colecao(self) -> int | None:
        """Dimensão configurada na coleção, ou `None` se ela não existe."""
        if not self.colecao_existe():
            return None
        info = self._cliente.get_collection(self._config.colecao)
        return info.config.params.vectors.size

    def contar_pontos(self) -> int:
        if not self.colecao_existe():
            return 0
        return self._cliente.get_collection(self._config.colecao).points_count or 0

    # ── escrita ───────────────────────────────────────────────────────────

    def garantir_colecao(self, dimensao: int, recriar: bool = False) -> None:
        """Cria a coleção, ou valida a existente contra a dimensão esperada.

        Esta validação é a correção da armadilha mais cara do projeto: antes, a
        coleção existente era reaproveitada em silêncio mesmo tendo sido criada
        com outro modelo de embedding, e a falha só aparecia lotes adiante,
        como erro de dimensão vindo do servidor.
        """
        try:
            if recriar and self.colecao_existe():
                self._cliente.delete_collection(self._config.colecao)

            existente = self.dimensao_da_colecao()

            if existente is None:
                self._cliente.create_collection(
                    collection_name=self._config.colecao,
                    vectors_config=VectorParams(size=dimensao, distance=Distance.COSINE),
                )
                return

            if existente != dimensao:
                raise ErroDimensaoIncompativel(
                    f"A coleção '{self._config.colecao}' tem vetores de {existente} dimensões, "
                    f"mas o modelo de embedding atual produz {dimensao}.",
                    sugestao=(
                        "A coleção foi criada com outro modelo. Recrie-a (a indexação oferece "
                        "essa opção) ou volte o modelo de embedding anterior — indexar assim "
                        "falharia lote a lote."
                    ),
                )
        except ErroDimensaoIncompativel:
            raise
        except Exception as erro:
            raise self._erro_conexao(erro) from erro

    def ids_existentes(self, chunk_ids: list[str]) -> set[str]:
        """Subconjunto de `chunk_ids` já presente no índice.

        Permite retomar uma indexação interrompida sem repetir o embedding dos
        chunks já processados — que é a parte cara, medida em horas.
        """
        if not chunk_ids or not self.colecao_existe():
            return set()

        por_uuid = {id_do_chunk(c): c for c in chunk_ids}
        try:
            encontrados = self._cliente.retrieve(
                collection_name=self._config.colecao,
                ids=list(por_uuid),
                with_payload=False,
                with_vectors=False,
            )
        except Exception as erro:
            raise self._erro_conexao(erro) from erro

        return {por_uuid[str(ponto.id)] for ponto in encontrados if str(ponto.id) in por_uuid}

    def inserir(self, chunks: list[Chunk], vetores: list[list[float]]) -> int:
        """Grava os chunks com seus vetores. `strict` protege contra desalinhamento."""
        pontos = [
            PointStruct(id=id_do_chunk(chunk.chunk_id), vector=vetor, payload=chunk.como_dicionario())
            for chunk, vetor in zip(chunks, vetores, strict=True)
        ]
        try:
            self._cliente.upsert(collection_name=self._config.colecao, points=pontos)
        except Exception as erro:
            raise self._erro_conexao(erro) from erro
        return len(pontos)

    # ── leitura ───────────────────────────────────────────────────────────

    def buscar(self, vetor: list[float], k: int, score_minimo: float = 0.0) -> list[TrechoRecuperado]:
        try:
            pontos = self._cliente.query_points(
                collection_name=self._config.colecao,
                query=vetor,
                limit=k,
                score_threshold=score_minimo or None,
            ).points
        except Exception as erro:
            raise self._erro_conexao(erro) from erro

        return [
            TrechoRecuperado(
                texto=ponto.payload.get("texto", ""),
                titulo_pagina=ponto.payload.get("titulo_pagina", "?"),
                documento_origem=ponto.payload.get("documento_origem", "?"),
                chunk_id=ponto.payload.get("chunk_id", str(ponto.id)),
                score=ponto.score,
            )
            for ponto in pontos
        ]

    # ── interno ───────────────────────────────────────────────────────────

    def _erro_conexao(self, erro: Exception) -> ErroPipeline:
        """Traduz a exceção do cliente para o erro que descreve a causa real.

        O cliente do Qdrant embrulha tudo no mesmo tipo, inclusive o 404 de
        coleção inexistente — que reportado como falha de conexão manda o
        usuário reiniciar um serviço que está de pé, enquanto o que falta é
        rodar a indexação.
        """
        texto = str(erro)

        if "doesn't exist" in texto or "Not found" in texto:
            return ErroPreRequisito(
                f"A coleção '{self._config.colecao}' não existe no Qdrant.",
                sugestao="Rode a indexação para criá-la, ou aponte para outra coleção com --colecao.",
            )

        # A resposta crua do servidor tem várias linhas de JSON; só a primeira
        # linha diz algo útil numa mensagem de terminal.
        resumo = texto.strip().splitlines()[0]
        return ErroConexao(
            f"Falha ao falar com o Qdrant em {self._config.url}: {resumo}",
            sugestao="Suba o serviço com `podman compose up -d` (podman, não docker).",
        )
