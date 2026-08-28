"""
Orquestrador — fecha o ciclo completo do RAG: pergunta → recuperação →
prompt aumentado → geração. É a peça "cinza" que amarra as peças "roxas"
(Ollama, Qdrant), no sentido dos diagramas que já vimos.

Pensado pra já servir de base pra implementação real da IA Freiriana, não
só de teste: os nomes de modelo/coleção ficam como configuração no topo
(troca de collection = trocar UESP_LORE por corpus_ipf, por exemplo), e o
prompt de geração é uma função isolada — na implementação real, essa função
vira o lugar onde entra o marco pedagógico (problematizar antes de
responder, exigir citação por afirmação, buscar posições divergentes,
recusar produto acabado), no lugar do prompt genérico de teste que está
aqui agora.

Extensão futura combinada, ainda não implementada: um "intermediador" entre
a pergunta e a busca — decompõe perguntas compostas em sub-perguntas antes
de buscar (ver marcação NOTE abaixo, no lugar exato onde isso entraria).

Rode:  python3 src/orquestrador.py
"""

import requests
from qdrant_client import QdrantClient

OLLAMA_URL = "http://localhost:11434"
MODELO_EMBEDDING = "bge-m3"
MODELO_GERACAO = "qwen2.5:7b"

QDRANT_URL = "http://localhost:6333"
NOME_COLECAO = "uesp_lore"  # trocar pela coleção do corpus real quando for o caso

K_BUSCA = 5

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


def buscar(pergunta: str, k: int = K_BUSCA):
    # NOTE: é aqui que entraria o intermediador de decomposição de consulta,
    # combinado pra depois — pergunta composta vira N sub-perguntas, cada
    # uma busca separadamente, os resultados se combinam antes do prompt.
    vetor = embutir_pergunta(pergunta)
    return cliente_qdrant.query_points(
        collection_name=NOME_COLECAO,
        query=vetor,
        limit=k,
    ).points


def montar_prompt(pergunta: str, resultados) -> str:
    trechos_formatados = "\n\n".join(
        f"[Fonte: {r.payload.get('titulo_pagina', '?')}]\n{r.payload.get('texto', '')}" for r in resultados
    )
    return f"""Você responde SOMENTE com base nos trechos abaixo, que estão em inglês. \
Responda em português. Cite a fonte (o nome entre colchetes) de cada afirmação. \
Se os trechos não tiverem a resposta, diga isso claramente em vez de inventar.

TRECHOS RECUPERADOS:
{trechos_formatados}

PERGUNTA:
{pergunta}
"""


def gerar_resposta(prompt: str) -> str:
    resp = sessao.post(
        f"{OLLAMA_URL}/api/generate",
        json={
            "model": MODELO_GERACAO,
            "prompt": prompt,
            "stream": False,
        },
        timeout=180,
    )
    resp.raise_for_status()
    return resp.json()["response"]


def responder(pergunta: str) -> None:
    print("=" * 78)
    print(f"PERGUNTA: {pergunta}\n")

    resultados = buscar(pergunta, k=K_BUSCA)

    print(f"Recuperados: {len(resultados)}")
    for r in resultados:
        print(f"  score={r.score:.3f}  [{r.payload.get('titulo_pagina', '?')}]")

    prompt = montar_prompt(pergunta, resultados)
    print("\nGerando resposta...\n")
    resposta = gerar_resposta(prompt)
    print(f"RESPOSTA:\n{resposta}\n")


if __name__ == "__main__":
    perguntas_teste = [
        "Quem são os Argonianos e de onde eles vêm?",
        "O que aconteceu na Crise de Oblivion?",
    ]

    for pergunta in perguntas_teste:
        responder(pergunta)
