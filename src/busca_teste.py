"""
Teste de recuperação — pergunta em português, embedding via Ollama (bge-m3),
busca no Qdrant. Sem LLM de geração envolvido: isso mede só a camada de
recuperação, que é o que decidimos testar primeiro (fase-3-avaliacao-e-servidor.md:
recall@k avaliável isoladamente, sem gerar nenhuma linha de texto).

Rode:  python3 src/busca_teste.py
"""

import requests
from qdrant_client import QdrantClient

OLLAMA_URL = "http://localhost:11434"
MODELO_EMBEDDING = "bge-m3"

QDRANT_URL = "http://localhost:6333"
NOME_COLECAO = "uesp_lore"

sessao = requests.Session()
cliente_qdrant = QdrantClient(url=QDRANT_URL)


def embutir_pergunta(pergunta: str) -> list[float]:
    resp = sessao.post(
        f"{OLLAMA_URL}/api/embed",
        json={
            "model": MODELO_EMBEDDING,
            "input": [pergunta],
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["embeddings"][0]


def buscar(pergunta: str, k: int = 5):
    vetor = embutir_pergunta(pergunta)
    resultados = cliente_qdrant.query_points(
        collection_name=NOME_COLECAO,
        query=vetor,
        limit=k,
    ).points
    return resultados


def verificar_colecao():
    info = cliente_qdrant.get_collection(NOME_COLECAO)
    print(f"Coleção '{NOME_COLECAO}': {info.points_count} pontos indexados.\n")


if __name__ == "__main__":
    verificar_colecao()

    perguntas_teste = [
        "Quem são os Argonianos e de onde eles vêm?",
        "O que aconteceu na Crise de Oblivion?",
        "Quais são os deuses adorados pelos Nórdicos?",
        "Como funciona a magia de Restauração?",
    ]

    for pergunta in perguntas_teste:
        print("=" * 78)
        print(f"PERGUNTA (pt-br): {pergunta}\n")

        resultados = buscar(pergunta, k=5)
        for r in resultados:
            titulo = r.payload.get("titulo_pagina", "?")
            preview = r.payload.get("texto", "")[:150].replace("\n", " ")
            print(f"  score={r.score:.3f}  [{titulo}]  {preview}...")
        print()
