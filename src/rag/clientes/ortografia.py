"""
Verificação ortográfica pelo `hunspell`, chamado por subprocess.

Serve à avaliação do OCR: a fração de palavras que o dicionário não conhece é
um indicador de qualidade que não precisa de transcrição de referência. Sem o
dicionário do idioma, devolve `None` em vez de errar — o indicador some, a
avaliação continua.
"""

import subprocess

# Pacote de idioma do Tesseract → dicionário do hunspell.
DICIONARIOS = {"por": "pt_BR", "eng": "en_US", "spa": "es_ES", "fra": "fr_FR", "deu": "de_DE", "ita": "it_IT"}


def palavras_desconhecidas(palavras: list[str], idioma: str) -> set[str] | None:
    """As palavras que o dicionário do idioma não conhece, ou `None` sem dicionário."""
    dicionario = DICIONARIOS.get(idioma)
    if not dicionario:
        return None
    try:
        processo = subprocess.run(
            ["hunspell", "-l", "-d", dicionario],
            input="\n".join(palavras),
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except FileNotFoundError:
        return None
    # O hunspell sai com 0 mesmo sem o dicionário, e só reclama no stderr.
    if processo.returncode != 0 or "Can't open" in processo.stderr:
        return None
    return {linha.strip() for linha in processo.stdout.splitlines() if linha.strip()}


def sugestoes(palavras: list[str], idioma: str) -> dict[str, list[str]] | None:
    """As sugestões do dicionário para cada palavra que ele não conhece, ou `None` sem dicionário.

    Serve para **detectar** acento perdido (`circulos` → `círculos`), nunca para
    trocar a palavra: a escolha automática entre sugestões é o erro mais caro
    do registro de revisão do OCR.
    """
    dicionario = DICIONARIOS.get(idioma)
    if not dicionario or not palavras:
        return None if not dicionario else {}
    try:
        processo = subprocess.run(
            ["hunspell", "-a", "-d", dicionario],
            input="\n".join(palavras),
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except FileNotFoundError:
        return None
    if processo.returncode != 0 or "Can't open" in processo.stderr:
        return None
    # `& palavra N deslocamento: s1, s2` para a que tem sugestão; `#` sem sugestão; `*` conhecida.
    resultado: dict[str, list[str]] = {}
    for linha in processo.stdout.splitlines():
        if linha.startswith("& "):
            cabeca, _, lista = linha[2:].partition(": ")
            resultado[cabeca.split(" ")[0]] = [s.strip() for s in lista.split(",") if s.strip()]
    return resultado
