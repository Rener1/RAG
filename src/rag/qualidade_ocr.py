"""
Indicadores de qualidade do texto que não precisam de transcrição de referência.

Puro: quem consulta o dicionário é o `VerificadorDePalavras` recebido
(`protocolos.py`). Fica na raiz do pacote porque a extração, a normalização e a
avaliação do OCR usam os mesmos indicadores, e uma etapa não importa outra.
"""

import unicodedata
from collections import Counter

from .config import ConfigQualidade
from .protocolos import SugeridorDePalavras, VerificadorDePalavras
from .texto_posicionado import TIPO_TEXTO, Caixa, PaginaPosicionada, Regiao, caixa_de

NIVEL_BOM = "bom"
NIVEL_REGULAR = "regular"
NIVEL_RUIM = "ruim"
NIVEL_SEM_MEDIDA = "sem medida"
NIVEL_ORIGINAL = "texto original"
NIVEIS = (NIVEL_BOM, NIVEL_REGULAR, NIVEL_RUIM, NIVEL_SEM_MEDIDA, NIVEL_ORIGINAL)

# Tirado das pontas da palavra antes de consultar o dicionário.
PONTUACAO_DAS_PONTAS = ".,;:!?()[]\"'“”«»—–-…¬"


def palavras_do_texto(texto: str) -> list[str]:
    """As palavras só de letras, sem a pontuação das pontas, em NFC."""
    palavras = (p.strip(PONTUACAO_DAS_PONTAS) for p in unicodedata.normalize("NFC", texto).split())
    return [p for p in palavras if p.isalpha()]


def fracao_fora_do_dicionario(texto: str, idioma: str, verificador: VerificadorDePalavras | None) -> float | None:
    """Das palavras só de letras, quantas o dicionário não conhece. `None` sem dicionário ou sem palavra."""
    if verificador is None:
        return None
    palavras = palavras_do_texto(texto)
    if not palavras:
        return None
    desconhecidas = verificador(palavras, idioma)
    if desconhecidas is None:
        return None
    return sum(1 for p in palavras if p in desconhecidas) / len(palavras)


def sem_diacriticos(palavra: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", palavra) if not unicodedata.combining(c))


def so_falta_acento(palavra: str, sugestao: str) -> bool:
    """`circulos` → `círculos`: a mesma palavra, com a mesma caixa, só com acento a mais ou diferente.

    Palavra curta fica de fora: `pe` → `pé`, `va` → `vã` são tão prováveis quanto
    outra leitura qualquer, e diferença só de caixa (`aa` → `AA`) não é acento.
    """
    return len(palavra) >= 4 and sugestao != palavra and sem_diacriticos(sugestao) == sem_diacriticos(palavra)


def _caixa_da_regiao(regiao: Regiao) -> Caixa:
    if regiao.contorno:
        return caixa_de(regiao.contorno)
    pontos = tuple(p for linha in regiao.linhas for p in (linha.contorno or linha.linha_de_base))
    return caixa_de(pontos)


def tem_colunas(pagina: PaginaPosicionada) -> bool:
    """Duas regiões de texto lado a lado, na mesma faixa da página: a ordem de leitura precisa de olho (P6).

    Lado a lado é não se sobrepor na horizontal; mesma faixa é dividir mais da
    metade da altura da menor. Região de uma linha só fica de fora: título e
    número soltos ao lado do texto não são coluna.
    """
    caixas = [_caixa_da_regiao(r) for r in pagina.regioes if r.tipo == TIPO_TEXTO and len(r.linhas) >= 2]
    for i, a in enumerate(caixas):
        for b in caixas[i + 1 :]:
            lado_a_lado = a[2] <= b[0] or b[2] <= a[0]
            faixa = min(a[3], b[3]) - max(a[1], b[1])
            menor = min(a[3] - a[1], b[3] - b[1])
            if lado_a_lado and menor > 0 and faixa > menor / 2:
                return True
    return False


def _confiancas(pagina: PaginaPosicionada, ignorar: frozenset[str], baixa: float) -> tuple[list[float], int]:
    """A confiança de cada palavra fora das regiões ignoradas, e quantas linhas são hesitantes."""
    valores, linhas_hesitantes = [], 0
    for regiao in pagina.regioes:
        if regiao.tipo in ignorar:
            continue
        for linha in regiao.linhas:
            da_linha = [p.confianca for p in linha.palavras if p.confianca is not None]
            valores += da_linha
            if da_linha and sum(da_linha) / len(da_linha) < baixa:
                linhas_hesitantes += 1
    return valores, linhas_hesitantes


def indicadores_da_pagina(
    texto: str,
    idioma: str,
    config: ConfigQualidade,
    verificador: VerificadorDePalavras | None = None,
    sugeridor: SugeridorDePalavras | None = None,
    posicionada: PaginaPosicionada | None = None,
    ignorar: frozenset[str] = frozenset(),
) -> dict:
    """Tudo o que se sabe da qualidade de uma página sem transcrição de referência.

    Campo que não se pode medir (sem dicionário, sem coordenadas) vem `None`,
    nunca zero: zero diria "medido e sem problema".
    """
    palavras = palavras_do_texto(texto)
    caracteres = sum(1 for c in texto if c.isalnum())
    indicadores: dict = {
        "caracteres": caracteres,
        "palavras": len(palavras),
        "fora_do_dicionario": None,
        "possiveis_nomes": None,
        "suspeitas": [],
        "acentos_perdidos": None,
        "exemplos_de_acento": [],
        "idioma_suspeito": None,
        "confianca_media": None,
        "fracao_hesitante": None,
        "linhas_hesitantes": None,
        "regioes_de_texto": None,
        "colunas": None,
    }

    desconhecidas = verificador(sorted(set(palavras)), idioma) if verificador and palavras else None
    if desconhecidas is not None:
        minusculas = [p for p in palavras if p[0].islower()]
        erradas = [p for p in minusculas if p in desconhecidas]
        indicadores["fora_do_dicionario"] = len(erradas) / len(minusculas) if minusculas else None
        indicadores["possiveis_nomes"] = sum(1 for p in palavras if p[0].isupper() and p in desconhecidas)
        indicadores["suspeitas"] = [p for p, _ in Counter(erradas).most_common(config.palavras_suspeitas)]
        fracao = indicadores["fora_do_dicionario"]
        if sugeridor and erradas:
            conjunto_errado = set(erradas)
            sugestoes = sugeridor(sorted(conjunto_errado), idioma)
            if sugestoes is not None:
                com_acento = {
                    p: s
                    for p, lista in sugestoes.items()
                    if p in conjunto_errado
                    for s in lista[:3]
                    if so_falta_acento(p, s)
                }
                indicadores["acentos_perdidos"] = sum(1 for p in erradas if p in com_acento)
                indicadores["exemplos_de_acento"] = [f"{p} → {s}" for p, s in list(com_acento.items())[:5]]
        if fracao is not None and fracao > config.limiar_de_idioma and verificador:
            indicadores["idioma_suspeito"] = _idioma_melhor(minusculas, idioma, fracao, verificador, config)

    if posicionada is not None and posicionada.tem_posicao:
        valores, hesitantes = _confiancas(posicionada, ignorar, config.confianca_baixa)
        if valores:
            indicadores["confianca_media"] = sum(valores) / len(valores)
            indicadores["fracao_hesitante"] = sum(1 for v in valores if v < config.confianca_baixa) / len(valores)
        indicadores["linhas_hesitantes"] = hesitantes
        indicadores["regioes_de_texto"] = sum(1 for r in posicionada.regioes if r.tipo == TIPO_TEXTO)
        indicadores["colunas"] = tem_colunas(posicionada)
    return indicadores


def _idioma_melhor(
    minusculas: list[str], idioma: str, fracao: float, verificador: VerificadorDePalavras, config: ConfigQualidade
) -> str | None:
    """Outro idioma em que o texto erra menos da metade: o catálogo pode estar errado, ou o OCR."""
    melhor, menor = None, fracao / 2
    for outro in (i for i in config.idiomas_testados.split("|") if i and i != idioma):
        desconhecidas = verificador(sorted(set(minusculas)), outro)
        if desconhecidas is None:
            continue
        fracao_outro = sum(1 for p in minusculas if p in desconhecidas) / len(minusculas)
        if fracao_outro < menor:
            melhor, menor = outro, fracao_outro
    return melhor


def detectar_idioma(texto: str, verificador: VerificadorDePalavras, config: ConfigQualidade) -> str:
    """O idioma em que o texto erra menos no dicionário, se errar menos da metade. Vazio se nenhum.

    Para o item sem idioma no catálogo (ou `other`): sem isso ele ficaria sem
    medida nenhuma. É palpite pelo dicionário, e o relatório o mostra como tal.
    """
    minusculas = [p for p in palavras_do_texto(texto) if p[0].islower()]
    if not minusculas:
        return ""
    melhor, menor = "", 0.5
    for idioma in (i for i in config.idiomas_testados.split("|") if i):
        desconhecidas = verificador(sorted(set(minusculas)), idioma)
        if desconhecidas is None:
            continue
        fracao = sum(1 for p in minusculas if p in desconhecidas) / len(minusculas)
        if fracao < menor:
            melhor, menor = idioma, fracao
    return melhor


def nivel_da_pagina(indicadores: dict, origem: str, config: ConfigQualidade) -> str:
    """Bom, regular ou ruim pelo dicionário, um nível abaixo se o Kraken hesitou demais.

    Texto original (camada digital do próprio PDF) não é medido como OCR.
    Página vazia é ruim: é o P1, a página perdida.
    """
    if origem == "digital_nativo":
        return NIVEL_ORIGINAL
    if indicadores["caracteres"] == 0 or origem == "sem_texto":
        return NIVEL_RUIM
    fracao = indicadores["fora_do_dicionario"]
    if fracao is None or indicadores["palavras"] < config.minimo_de_palavras:
        return NIVEL_SEM_MEDIDA
    ordem = [NIVEL_BOM, NIVEL_REGULAR, NIVEL_RUIM]
    posicao = 0 if fracao <= config.limiar_bom else 1 if fracao <= config.limiar_regular else 2
    hesitante = indicadores["fracao_hesitante"]
    if hesitante is not None and hesitante > config.fracao_hesitante:
        posicao = min(posicao + 1, 2)
    return ordem[posicao]


# ── o documento inteiro, para o relatório ─────────────────────────────────

ROTULOS_DE_ORIGEM = {
    "digital_nativo": "texto original (digital)",
    "ocr": "OCR",
    "ocr_anterior": "OCR anterior mantido",
    "sem_texto": "sem texto",
}

# O que cada código do registro de revisão do OCR quer dizer, na legenda.
PROBLEMAS = {
    "P1": "Página perdida: ficou sem texto depois do OCR",
    "P2": "Reconhecimento: acentos perdidos e palavras fora do dicionário",
    "P3": "Idioma: o texto erra muito menos no dicionário de outro idioma que no do catálogo",
    "P6": "Ordem de leitura: colunas lado a lado — conferir na imagem se a ordem está certa",
    "P7": "Linhas de baixa confiança fora do carimbo e do ruído: caneta, carimbo de outro tipo, mancha",
    "P8": "Carimbo e ruído de digitalização tirados do texto (informativo: já tratado)",
    "P4": "Palavras partidas no fim da linha, juntadas (informativo: já tratado)",
}


def _media_ponderada(paginas: list[dict], campo: str) -> float | None:
    pares = [(p[campo], p["palavras"]) for p in paginas if p.get(campo) is not None and p["palavras"]]
    peso = sum(n for _, n in pares)
    return sum(v * n for v, n in pares) / peso if peso else None


def _lista_de_paginas(numeros: list[int]) -> str:
    return ", ".join(str(n) for n in numeros[:12]) + (" …" if len(numeros) > 12 else "")


def nivel_do_documento(paginas: list[dict], config: ConfigQualidade) -> str:
    """O nível do texto inteiro: a fração do dicionário ponderada pelas palavras das páginas medidas."""
    if paginas and all(p["nivel"] == NIVEL_ORIGINAL for p in paginas):
        return NIVEL_ORIGINAL
    medidas = [p for p in paginas if p["nivel"] in (NIVEL_BOM, NIVEL_REGULAR, NIVEL_RUIM) and p["caracteres"]]
    if not medidas:
        return NIVEL_RUIM if any(p["nivel"] == NIVEL_RUIM for p in paginas) else NIVEL_SEM_MEDIDA
    agregado = {
        "fora_do_dicionario": _media_ponderada(medidas, "fora_do_dicionario"),
        "fracao_hesitante": _media_ponderada(medidas, "fracao_hesitante"),
        "palavras": sum(p["palavras"] for p in medidas),
        "caracteres": sum(p["caracteres"] for p in medidas),
    }
    return nivel_da_pagina(agregado, "ocr", config)


def resumo_do_documento(qualidade: dict, config: ConfigQualidade, anterior: dict | None = None) -> dict:
    """Uma linha da planilha: o documento, o nível e os principais problemas, do mais grave ao informativo.

    `anterior` é o `.qualidade.json` do mesmo PDF numa extração anterior (a do
    Tesseract), para a comparação lado a lado.
    """
    paginas = qualidade["paginas"]
    contagem_de_origem = Counter(p["origem"] for p in paginas)
    comparacao = qualidade.get("comparacao_ocr_anterior") or {}
    substituidas = sorted(int(n) for n, c in comparacao.items() if c["escolhido"] == "ocr")
    mantidas = sorted(int(n) for n, c in comparacao.items() if c["escolhido"] == "ocr_anterior")

    vazias = [
        p["pagina"]
        for p in paginas
        if p["nivel"] == NIVEL_RUIM and (p["caracteres"] == 0 or p["origem"] == "sem_texto")
    ]
    colunas = [p["pagina"] for p in paginas if p.get("colunas")]
    idiomas = Counter(p["idioma_suspeito"] for p in paginas if p.get("idioma_suspeito"))
    acentos = sum(p["acentos_perdidos"] or 0 for p in paginas)
    exemplos_de_acento = [e for p in paginas for e in p.get("exemplos_de_acento", [])][:3]
    hesitantes = sum(p["linhas_hesitantes"] or 0 for p in paginas)
    fracao = _media_ponderada([p for p in paginas if p["origem"] != "digital_nativo"], "fora_do_dicionario")
    regras = Counter()
    for p in paginas:
        regras.update(p.get("regras", {}))
    linhas_por_tipo = qualidade.get("linhas_por_tipo", {})
    sem_dicionario = all(p["fora_do_dicionario"] is None for p in paginas if p["caracteres"])

    problemas = []
    if vazias:
        problemas.append(f"P1 · {len(vazias)} página(s) sem texto: {_lista_de_paginas(vazias)}")
    if idiomas:
        outro, n = idiomas.most_common(1)[0]
        problemas.append(f"P3 · {n} página(s) leem melhor em {outro} que em {qualidade['idioma'] or '?'}")
    if acentos:
        problemas.append(
            f"P2 · {acentos} acento(s) perdido(s)"
            + (f" (ex.: {'; '.join(exemplos_de_acento)})" if exemplos_de_acento else "")
        )
    if fracao is not None and fracao > config.limiar_regular:
        problemas.append(f"P2 · {fracao:.0%} das palavras fora do dicionário")
    if colunas:
        problemas.append(f"P6 · colunas nas páginas {_lista_de_paginas(colunas)}: conferir a ordem de leitura")
    if hesitantes >= 3:
        problemas.append(f"P7 · {hesitantes} linha(s) de baixa confiança")
    if sem_dicionario and any(p["origem"] != "digital_nativo" for p in paginas):
        problemas.append("sem dicionário para o idioma: qualidade não medida")
    if mantidas:
        problemas.append(f"OCR anterior melhor que o Kraken nas páginas {_lista_de_paginas(mantidas)}: mantido")
    if substituidas:
        problemas.append(f"OCR anterior substituído pelo Kraken nas páginas {_lista_de_paginas(substituidas)}")
    tirados = {t: n for t, n in linhas_por_tipo.items() if t in ("carimbo", "ruido") and n}
    if tirados:
        problemas.append(
            "P8 · tirados do texto: " + ", ".join(f"{n} linha(s) de {t}" for t, n in sorted(tirados.items()))
        )
    juntadas = regras["hifen_marcado"] + regras["hifen_comum"] + regras["sem_hifen"]
    if juntadas:
        problemas.append(f"P4 · {juntadas} palavra(s) partida(s) juntada(s)")

    ferramenta = qualidade.get("ocr_ferramenta", "").lower()
    motor = "Kraken" if "kraken" in ferramenta else "Tesseract" if "tesseract" in ferramenta else ""
    if mantidas and not contagem_de_origem["ocr"]:
        origem = "OCR anterior mantido"
    elif contagem_de_origem["ocr"] and (substituidas or mantidas):
        origem = f"OCR anterior substituído pelo {motor}" if not mantidas else f"misto: {motor} e OCR anterior"
    elif contagem_de_origem["ocr"] and contagem_de_origem["digital_nativo"]:
        origem = f"misto: texto original e OCR {motor}"
    elif contagem_de_origem["ocr"]:
        origem = f"OCR {motor}"
    elif contagem_de_origem["digital_nativo"]:
        origem = "texto original (digital)"
    else:
        origem = "sem texto"

    suspeitas = Counter()
    for p in paginas:
        suspeitas.update(p.get("suspeitas", []))
    niveis_das_paginas = Counter(p["nivel"] for p in paginas)
    pior = next((n for n in (NIVEL_RUIM, NIVEL_REGULAR, NIVEL_BOM) if niveis_das_paginas[n]), None)
    return {
        "handle": qualidade["handle"],
        "arquivo": qualidade["arquivo"],
        "idioma": qualidade["idioma"]
        + (" (detectado; catálogo sem idioma)" if qualidade.get("idioma_detectado") else ""),
        "origem": origem,
        "paginas": len(paginas),
        "paginas_ocr": contagem_de_origem["ocr"],
        "paginas_ocr_anterior": contagem_de_origem["ocr_anterior"],
        "paginas_originais": contagem_de_origem["digital_nativo"],
        "paginas_vazias": len(vazias),
        "nivel": nivel_do_documento(paginas, config),
        "pior_pagina": pior,
        "niveis_das_paginas": dict(niveis_das_paginas),
        "fora_do_dicionario": fracao,
        "fora_do_dicionario_anterior": (
            _media_ponderada([p for p in anterior["paginas"] if p["origem"] != "digital_nativo"], "fora_do_dicionario")
            if anterior
            else None
        ),
        "acentos_perdidos": acentos if not sem_dicionario else None,
        "confianca_media": _media_ponderada(paginas, "confianca_media"),
        "linhas_de_carimbo": linhas_por_tipo.get("carimbo", 0),
        "linhas_de_ruido": linhas_por_tipo.get("ruido", 0),
        "palavras_juntadas": juntadas,
        "problemas": problemas,
        "suspeitas": [p for p, _ in suspeitas.most_common(config.palavras_suspeitas)],
    }
