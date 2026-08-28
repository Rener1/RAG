"""
Embedding + indexação — lê data/chunks.jsonl, gera o vetor de cada chunk via
Ollama (bge-m3) e insere no Qdrant junto com o payload de proveniência.

Essas duas coisas (embedding e indexação) são a mesma etapa na prática: um
vetor sem lugar pra ser buscado não serve pra nada, então geramos e já
inserimos juntos.

Paraleliza em lotes, pelo mesmo motivo do download: uma chamada por chunk
seria lenta por espera de rede/processamento, não por volume de dado real.

Pré-requisitos:
  ollama pull bge-m3
  podman compose up -d   (Qdrant rodando em localhost:6333)
  pip install qdrant-client requests

Rode:  python3 src/embedding_e_indexacao.py
"""

import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

RAIZ_PROJETO = Path(__file__).resolve().parents[1]  # paths independem de onde o script é chamado

ARQUIVO_CHUNKS = RAIZ_PROJETO / "data" / "chunks.jsonl"
OLLAMA_URL = "http://localhost:11434"
MODELO_EMBEDDING = "bge-m3"
DIMENSAO_VETOR = 1024  # tem que bater com a saída do bge-m3

QDRANT_URL = "http://localhost:6333"
NOME_COLECAO = "uesp_lore"

TAMANHO_LOTE = 16  # chunks por chamada ao Ollama
LOTES_PARALELOS = 4  # chamadas simultâneas — modesto: é processamento local, não so espera de rede

sessao = requests.Session()
cliente_qdrant = QdrantClient(url=QDRANT_URL)
lock = threading.Lock()


def carregar_chunks(caminho: str) -> list[dict]:
    chunks = []
    with open(caminho, encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if linha:
                chunks.append(json.loads(linha))
    return chunks


def garantir_colecao():
    colecoes_existentes = [c.name for c in cliente_qdrant.get_collections().collections]
    if NOME_COLECAO in colecoes_existentes:
        print(f"Coleção '{NOME_COLECAO}' já existe — reaproveitando.")
        return

    cliente_qdrant.create_collection(
        collection_name=NOME_COLECAO,
        vectors_config=VectorParams(size=DIMENSAO_VETOR, distance=Distance.COSINE),
    )
    print(f"Coleção '{NOME_COLECAO}' criada (vetor de {DIMENSAO_VETOR} dimensões, distância cosseno).")


def gerar_embeddings_em_lote(textos: list[str]) -> list[list[float]]:
    resp = sessao.post(
        f"{OLLAMA_URL}/api/embed",
        json={
            "model": MODELO_EMBEDDING,
            "input": textos,
        },
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["embeddings"]


def id_deterministico(chunk_id: str) -> str:
    """Qdrant exige ID em formato UUID ou inteiro — gera um UUID estável a
    partir do chunk_id, assim rodar de novo sobrescreve em vez de duplicar."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk_id))


def processar_lote(lote_chunks: list[dict]) -> int:
    textos = [c["texto"] for c in lote_chunks]
    vetores = gerar_embeddings_em_lote(textos)

    pontos = [
        PointStruct(
            id=id_deterministico(chunk["chunk_id"]),
            vector=vetor,
            payload={
                "chunk_id": chunk["chunk_id"],
                "texto": chunk["texto"],
                "documento_origem": chunk["documento_origem"],
                "titulo_pagina": chunk["titulo_pagina"],
                "chunk_index": chunk["chunk_index"],
            },
        )
        for chunk, vetor in zip(lote_chunks, vetores)
    ]

    cliente_qdrant.upsert(collection_name=NOME_COLECAO, points=pontos)
    return len(pontos)


if __name__ == "__main__":
    garantir_colecao()

    chunks = carregar_chunks(ARQUIVO_CHUNKS)
    print(f"{len(chunks)} chunks carregados de {ARQUIVO_CHUNKS}.")

    lotes = [chunks[i : i + TAMANHO_LOTE] for i in range(0, len(chunks), TAMANHO_LOTE)]
    print(f"Agrupados em {len(lotes)} lotes de até {TAMANHO_LOTE} chunks.")
    print(f"Gerando embeddings e indexando com {LOTES_PARALELOS} lotes simultâneos...\n")

    total_indexado = 0
    lotes_processados = 0

    with ThreadPoolExecutor(max_workers=LOTES_PARALELOS) as executor:
        futuros = {executor.submit(processar_lote, lote): lote for lote in lotes}

        for futuro in as_completed(futuros):
            try:
                n = futuro.result()
            except Exception as e:
                print(f"  um lote falhou: {e}")
                continue

            with lock:
                lotes_processados += 1
                total_indexado += n
                if lotes_processados % 20 == 0 or lotes_processados == len(lotes):
                    print(f"  progresso: {lotes_processados}/{len(lotes)} lotes  (indexados: {total_indexado})")

    print(f"\nTotal indexado: {total_indexado} chunks na coleção '{NOME_COLECAO}'.")
