"""
Baixa páginas do namespace Lore da UESP via API MediaWiki e salva como .txt
na pasta data/corpus_uesp/ — pronto pro chunking.

v4 — usa o endpoint de lote de verdade (prop=revisions, até 50 títulos por
requisição) em vez de prop=extracts (que trava em 1 página por requisição
pra texto completo). A troca: aqui vem o wikitext bruto, com marcação —
então usamos mwparserfromhell pra limpar isso localmente, sem gastar mais
nenhuma requisição de rede nisso.

Uso: apenas para teste pessoal do pipeline de RAG. O conteúdo da UESP é
licenciado sob CC BY-SA — se pretender usar além de teste local, confira
os termos em https://en.uesp.net/wiki/UESPWiki:Copyright antes.

Pré-requisito:  pip install mwparserfromhell requests
Rode:           python3 src/baixar_corpus_uesp.py
"""

import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import mwparserfromhell
import requests

RAIZ_PROJETO = Path(__file__).resolve().parents[1]  # paths independem de onde o script é chamado

API_URL = "https://en.uesp.net/w/api.php"
PASTA_SAIDA = RAIZ_PROJETO / "data" / "corpus_uesp"
TAMANHO_MINIMO = 80  # caracteres — filtra só o que é essencialmente vazio
CANDIDATOS_A_BUSCAR = 50000  # teto alto o suficiente pra cobrir o namespace inteiro
TITULOS_POR_LOTE = 50  # máximo aceito por requisição em prop=revisions
LOTES_PARALELOS = 8  # requisições de lote simultâneas

sessao = requests.Session()
lock = threading.Lock()


def descobrir_namespace_lore() -> int:
    resp = sessao.get(
        API_URL,
        params={
            "action": "query",
            "meta": "siteinfo",
            "siprop": "namespaces",
            "format": "json",
        },
        timeout=15,
    )
    resp.raise_for_status()
    namespaces = resp.json()["query"]["namespaces"]
    for ns_id, info in namespaces.items():
        if info.get("*") == "Lore" or info.get("canonical") == "Lore":
            return int(ns_id)
    raise RuntimeError("Namespace 'Lore' não encontrado.")


def listar_paginas_do_namespace(namespace_id: int, limite: int) -> list[str]:
    titulos: list[str] = []
    apcontinue = None
    while len(titulos) < limite:
        params = {
            "action": "query",
            "list": "allpages",
            "apnamespace": namespace_id,
            "aplimit": min(500, limite - len(titulos)),
            "format": "json",
        }
        if apcontinue:
            params["apcontinue"] = apcontinue
        resp = sessao.get(API_URL, params=params, timeout=15)
        resp.raise_for_status()
        dados = resp.json()
        paginas = dados.get("query", {}).get("allpages", [])
        titulos.extend(p["title"] for p in paginas)
        apcontinue = dados.get("continue", {}).get("apcontinue")
        if not apcontinue or not paginas:
            break
    return titulos[:limite]


def baixar_lote_wikitexto(titulos_lote: list[str]) -> dict[str, str]:
    """Uma requisição, até 50 páginas de wikitext bruto."""
    resp = sessao.get(
        API_URL,
        params={
            "action": "query",
            "prop": "revisions",
            "rvprop": "content",
            "rvslots": "main",
            "titles": "|".join(titulos_lote),
            "format": "json",
        },
        timeout=30,
    )
    resp.raise_for_status()
    paginas = resp.json().get("query", {}).get("pages", {})

    resultado = {}
    for pagina in paginas.values():
        titulo = pagina.get("title")
        revisoes = pagina.get("revisions")
        if not revisoes:
            continue  # página não existe ou foi apagada
        wikitexto = revisoes[0].get("slots", {}).get("main", {}).get("*", "")
        resultado[titulo] = wikitexto
    return resultado


def limpar_wikitexto(wikitexto: str) -> str:
    if wikitexto.strip().upper().startswith("#REDIRECT"):
        return ""  # redirect não tem conteúdo próprio

    # remove blocos <ref>...</ref> e <ref .../> antes de limpar o resto —
    # senão o texto da citação entra misturado no corpo do parágrafo
    sem_refs = re.sub(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>", "", wikitexto, flags=re.DOTALL | re.IGNORECASE)

    return mwparserfromhell.parse(sem_refs).strip_code().strip()


def nome_arquivo_seguro(titulo: str) -> str:
    return re.sub(r"[^\w\-]+", "_", titulo).strip("_") + ".txt"


def processar_lote(titulos_lote: list[str]) -> dict[str, int]:
    """Roda numa thread. Baixa um lote inteiro, limpa e salva cada página."""
    contagem = {"salvo": 0, "curto": 0}

    # não vale a pena baixar títulos cujo arquivo já existe — filtra antes da requisição
    a_baixar = [t for t in titulos_lote if not os.path.exists(os.path.join(PASTA_SAIDA, nome_arquivo_seguro(t)))]
    if not a_baixar:
        return contagem

    wikitextos = baixar_lote_wikitexto(a_baixar)

    for titulo, wikitexto in wikitextos.items():
        texto_limpo = limpar_wikitexto(wikitexto)
        if len(texto_limpo) < TAMANHO_MINIMO:
            contagem["curto"] += 1
            continue

        caminho = os.path.join(PASTA_SAIDA, nome_arquivo_seguro(titulo))
        with open(caminho, "w", encoding="utf-8") as f:
            f.write(f"# {titulo}\n\n{texto_limpo}")
        contagem["salvo"] += 1

    return contagem


if __name__ == "__main__":
    os.makedirs(PASTA_SAIDA, exist_ok=True)

    namespace_id = descobrir_namespace_lore()
    print(f"Namespace 'Lore' encontrado com id={namespace_id}.")

    titulos = listar_paginas_do_namespace(namespace_id, CANDIDATOS_A_BUSCAR)
    print(f"{len(titulos)} títulos encontrados no namespace Lore.")

    lotes = [titulos[i : i + TITULOS_POR_LOTE] for i in range(0, len(titulos), TITULOS_POR_LOTE)]
    print(f"Agrupados em {len(lotes)} lotes de até {TITULOS_POR_LOTE} páginas cada.")
    print(f"Baixando com {LOTES_PARALELOS} lotes simultâneos...\n")

    total_salvo = 0
    total_curto = 0
    lotes_processados = 0

    with ThreadPoolExecutor(max_workers=LOTES_PARALELOS) as executor:
        futuros = {executor.submit(processar_lote, lote): lote for lote in lotes}

        for futuro in as_completed(futuros):
            try:
                contagem = futuro.result()
            except Exception as e:
                print(f"  um lote falhou: {e}")
                continue

            with lock:
                lotes_processados += 1
                total_salvo += contagem["salvo"]
                total_curto += contagem["curto"]
                print(f"  lote {lotes_processados}/{len(lotes)}  (salvos até agora: {total_salvo})")

    print(f"\nTotal salvo: {total_salvo} páginas em {PASTA_SAIDA}/")
    print(f"Descartadas por estarem essencialmente vazias ou serem redirects: {total_curto}")
