"""
Sessão HTTP compartilhada, com repetição automática.

Os scripts originais criavam `requests.Session()` solto em cada arquivo e não
tratavam falha transitória: um 502 da wiki ou um timeout do Ollama derrubava o
lote inteiro, e o pipeline seguia com um buraco silencioso no meio.

Aqui a repetição fica na camada de transporte (urllib3), com espera
progressiva, e vale para todos os chamadores de uma vez.
"""

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def criar_sessao(
    *,
    tentativas: int = 3,
    espera_base: float = 0.5,
    conexoes_simultaneas: int = 16,
    user_agent: str = "",
) -> requests.Session:
    """Sessão com repetição em erro transitório e pool dimensionado.

    `conexoes_simultaneas` precisa acompanhar o número de threads que usam a
    sessão: com o pool menor que isso, o urllib3 descarta e reabre conexão a
    cada requisição excedente e avisa em log — foi o que acontecia no download
    com 8 threads sobre o pool padrão de 10.
    """
    sessao = requests.Session()

    politica = Retry(
        total=tentativas,
        backoff_factor=espera_base,  # espera 0.5s, 1s, 2s... entre as tentativas
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "POST"}),
        raise_on_status=False,
    )
    adaptador = HTTPAdapter(
        max_retries=politica,
        pool_connections=conexoes_simultaneas,
        pool_maxsize=conexoes_simultaneas,
    )
    sessao.mount("http://", adaptador)
    sessao.mount("https://", adaptador)

    if user_agent:
        sessao.headers["User-Agent"] = user_agent

    return sessao
