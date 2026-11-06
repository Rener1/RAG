"""
Relatório de qualidade do OCR: uma planilha com cada documento, o nível e os problemas.

Lê os `.qualidade.json` que `main.py normalizar` grava ao lado de cada PDF
extraído e monta as quatro abas: Resumo, Documentos, Páginas e Legenda. Quem
grava o `.xlsx` é `clientes/planilha.py`.

Mede o texto **normalizado**, que é o que o RAG vai usar. Os níveis vêm de
indicadores sem referência (dicionário e confiança do Kraken), com limiares
provisórios: a conferência por amostra está nas medições.
"""

import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from .clientes.planilha import Aba
from .config import ConfigQualidade
from .qualidade_ocr import (
    NIVEIS,
    NIVEL_BOM,
    NIVEL_ORIGINAL,
    NIVEL_REGULAR,
    NIVEL_RUIM,
    NIVEL_SEM_MEDIDA,
    PROBLEMAS,
    ROTULOS_DE_ORIGEM,
    resumo_do_documento,
)

SUFIXO_QUALIDADE = ".qualidade.json"

CORES_DOS_NIVEIS = {
    NIVEL_BOM: "C6EFCE",
    NIVEL_REGULAR: "FFEB9C",
    NIVEL_RUIM: "FFC7CE",
    NIVEL_SEM_MEDIDA: "D9D9D9",
    NIVEL_ORIGINAL: "DDEBF7",
}
# Do mais grave ao melhor, para a aba Documentos abrir pelo que precisa de atenção.
ORDEM_DOS_NIVEIS = {NIVEL_RUIM: 0, NIVEL_SEM_MEDIDA: 1, NIVEL_REGULAR: 2, NIVEL_BOM: 3, NIVEL_ORIGINAL: 4}

DESCRICAO_DOS_NIVEIS = {
    NIVEL_BOM: "até {bom:.0%} das palavras de inicial minúscula fora do dicionário",
    NIVEL_REGULAR: "até {regular:.0%} fora do dicionário",
    NIVEL_RUIM: "mais de {regular:.0%} fora do dicionário, ou página sem texto (P1)",
    NIVEL_SEM_MEDIDA: "sem dicionário para o idioma, ou página com menos de {minimo} palavras",
    NIVEL_ORIGINAL: "texto digital do próprio PDF, sem OCR: não é medido como OCR",
}


def ler_qualidades(pasta: Path) -> dict[tuple[str, str], dict]:
    """(handle, arquivo) → o `.qualidade.json` daquele PDF."""
    qualidades = {}
    for arquivo in sorted(pasta.glob(f"*/*{SUFIXO_QUALIDADE}")):
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
        qualidades[(dados["handle"], dados["arquivo"])] = dados
    return qualidades


def _porcentagem(valor: float | None) -> float | None:
    return None if valor is None else round(valor, 4)


def montar_abas(
    qualidades: dict[tuple[str, str], dict],
    titulos: dict[str, str],
    config: ConfigQualidade,
    data: str,
    anteriores: dict[tuple[str, str], dict] | None = None,
) -> tuple[list[Aba], list[dict]]:
    """As quatro abas, e os resumos por documento (que a ação também mostra no terminal)."""
    anteriores = anteriores or {}
    resumos = [resumo_do_documento(q, config, anteriores.get(chave)) for chave, q in qualidades.items()]
    resumos.sort(key=lambda r: (ORDEM_DOS_NIVEIS.get(r["nivel"], 9), r["handle"], r["arquivo"]))

    documentos = Aba(
        "Documentos",
        [
            "Handle",
            "Título",
            "Idioma",
            "Origem do texto",
            "Páginas",
            "Págs. OCR Kraken",
            "Págs. OCR anterior",
            "Págs. texto original",
            "Págs. sem texto",
            "Nível",
            "Pior página",
            "Páginas por nível",
            "Fora do dicionário (Kraken)",
            "Fora do dicionário (Tesseract)",
            "Acentos perdidos",
            "Confiança média",
            "Linhas de carimbo",
            "Linhas de ruído",
            "Palavras juntadas",
            "Principais problemas",
            "Palavras suspeitas",
            "Arquivo",
        ],  # fmt: skip
        [
            [
                r["handle"],
                titulos.get(r["handle"], ""),
                r["idioma"],
                r["origem"],
                r["paginas"],
                r["paginas_ocr"],
                r["paginas_ocr_anterior"],
                r["paginas_originais"],
                r["paginas_vazias"],
                r["nivel"],
                r["pior_pagina"],
                ", ".join(f"{n}: {r['niveis_das_paginas'][n]}" for n in NIVEIS if r["niveis_das_paginas"].get(n)),
                _porcentagem(r["fora_do_dicionario"]),
                _porcentagem(r["fora_do_dicionario_anterior"]),
                r["acentos_perdidos"],
                _porcentagem(r["confianca_media"]),
                r["linhas_de_carimbo"],
                r["linhas_de_ruido"],
                r["palavras_juntadas"],
                "\n".join(r["problemas"]),
                ", ".join(r["suspeitas"]),
                r["arquivo"],
            ]
            for r in resumos
        ],  # fmt: skip
        larguras={
            "Título": 40,
            "Origem do texto": 22,
            "Páginas por nível": 24,
            "Principais problemas": 60,
            "Palavras suspeitas": 40,
            "Arquivo": 22,
            "Handle": 12,
        },  # fmt: skip
        cores=CORES_DOS_NIVEIS,
        formatos={
            c: "0.0%" for c in ("Fora do dicionário (Kraken)", "Fora do dicionário (Tesseract)", "Confiança média")
        },  # fmt: skip
    )

    linhas_das_paginas = []
    for (handle, arquivo), q in sorted(qualidades.items()):
        comparacao = q.get("comparacao_ocr_anterior") or {}
        for p in q["paginas"]:
            c = comparacao.get(str(p["pagina"]), {})
            regras = p.get("regras", {})
            linhas_das_paginas.append(
                [
                    handle, arquivo, p["pagina"], ROTULOS_DE_ORIGEM.get(p["origem"], p["origem"]), p["nivel"],
                    _porcentagem(p["fora_do_dicionario"]), p["palavras"], p["acentos_perdidos"],
                    _porcentagem(p["confianca_media"]), _porcentagem(p["fracao_hesitante"]), p["linhas_hesitantes"],
                    "sim" if p.get("colunas") else "", p.get("idioma_suspeito") or "",
                    regras.get("hifen_marcado", 0) + regras.get("hifen_comum", 0) + regras.get("sem_hifen", 0),
                    regras.get("pontuacao", 0), _porcentagem(c.get("anterior")), _porcentagem(c.get("ocr")),
                    {"ocr": "Kraken", "ocr_anterior": "anterior"}.get(c.get("escolhido", ""), ""),
                    ", ".join(p.get("suspeitas", [])),
                ]
            )  # fmt: skip
    paginas = Aba(
        "Páginas",
        [
            "Handle",
            "Arquivo",
            "Página",
            "Origem",
            "Nível",
            "Fora do dicionário",
            "Palavras",
            "Acentos perdidos",
            "Confiança média",
            "Palavras hesitantes",
            "Linhas hesitantes",
            "Colunas",
            "Idioma suspeito",
            "Palavras juntadas",
            "Pontuação corrigida",
            "OCR anterior: fora do dicionário",
            "Kraken: fora do dicionário",
            "Leitura escolhida",
            "Palavras suspeitas",
        ],  # fmt: skip
        linhas_das_paginas,
        larguras={"Origem": 22, "Palavras suspeitas": 50, "Arquivo": 22},
        cores=CORES_DOS_NIVEIS,
        formatos={
            c: "0.0%"
            for c in (
                "Fora do dicionário",
                "Confiança média",
                "Palavras hesitantes",
                "OCR anterior: fora do dicionário",
                "Kraken: fora do dicionário",
            )
        },  # fmt: skip
    )

    resumo = Aba("Resumo", ["Item", "Valor"], _linhas_do_resumo(resumos, qualidades, config, data), com_filtro=False,
                 larguras={"Item": 50, "Valor": 60}, cores=CORES_DOS_NIVEIS)  # fmt: skip

    limiares = {"bom": config.limiar_bom, "regular": config.limiar_regular, "minimo": config.minimo_de_palavras}
    legenda = Aba(
        "Legenda",
        ["Nível ou código", "Significado"],
        [[n, DESCRICAO_DOS_NIVEIS[n].format(**limiares)] for n in NIVEIS]
        + [
            ["", ""],
            [
                "Agravante",
                f"mais de {config.fracao_hesitante:.0%} das palavras com confiança do Kraken "
                f"abaixo de {config.confianca_baixa} baixa um nível",
            ],
        ]
        + [["", ""]]
        + [[codigo, texto] for codigo, texto in PROBLEMAS.items()]
        + [
            ["", ""],
            [
                "Atenção",
                "P6 e P7 são sinais, não diagnóstico: confirmar exige olhar a página. Os limiares "
                "são provisórios (ver docs/engenharia/medicoes.md).",
            ],
        ],  # fmt: skip
        larguras={"Nível ou código": 18, "Significado": 100},
        cores=CORES_DOS_NIVEIS,
        com_filtro=False,
    )
    return [resumo, documentos, paginas, legenda], resumos


def _linhas_do_resumo(resumos: list[dict], qualidades: dict, config: ConfigQualidade, data: str) -> list[list]:
    paginas = [p for q in qualidades.values() for p in q["paginas"]]
    por_nivel_doc = Counter(r["nivel"] for r in resumos)
    por_nivel_pag = Counter(p["nivel"] for p in paginas)
    por_idioma = Counter(r["idioma"] or "(sem)" for r in resumos)
    motores = Counter(f"{q.get('ocr_ferramenta', '')} {q.get('ocr_versao', '')}".strip() for q in qualidades.values())
    linhas: list[list] = [
        ["Gerado em", data],
        ["Documentos (PDFs)", len(resumos)],
        ["Páginas", len(paginas)],
        ["Motor de OCR", "; ".join(m for m in motores if m) or "—"],
        ["", ""],
        ["Documentos por nível", ""],
    ]
    linhas += [[f"  {n}", por_nivel_doc[n]] for n in NIVEIS if por_nivel_doc[n]]
    linhas += [["", ""], ["Páginas por nível", ""]]
    linhas += [[f"  {n}", por_nivel_pag[n]] for n in NIVEIS if por_nivel_pag[n]]
    utilizaveis = por_nivel_pag[NIVEL_BOM] + por_nivel_pag[NIVEL_ORIGINAL]
    linhas += [
        ["", ""],
        ["Páginas boas ou com texto original", f"{utilizaveis} de {len(paginas)} ({utilizaveis / max(1, len(paginas)):.0%})"],
        ["", ""],
        ["Documentos por idioma", ", ".join(f"{i}: {n}" for i, n in sorted(por_idioma.items()))],
    ]  # fmt: skip
    comparados = [
        r for r in resumos if r["fora_do_dicionario"] is not None and r["fora_do_dicionario_anterior"] is not None
    ]
    if comparados:
        kraken = sum(r["fora_do_dicionario"] for r in comparados) / len(comparados)
        tesseract = sum(r["fora_do_dicionario_anterior"] for r in comparados) / len(comparados)
        linhas += [
            ["", ""],
            [f"Fora do dicionário, média de {len(comparados)} documentos", f"Kraken {kraken:.1%} · Tesseract {tesseract:.1%}"],
        ]  # fmt: skip
    regras = next(iter(qualidades.values()), {}).get("regras_de_normalizacao", {})
    linhas += [
        ["", ""],
        ["Regras de normalização", ", ".join(f"{k}={v}" for k, v in regras.items())],
        ["Limiares de qualidade", ", ".join(f"{k}={v}" for k, v in asdict(config).items())],
    ]
    return linhas
