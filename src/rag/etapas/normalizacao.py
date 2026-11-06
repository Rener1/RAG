"""
Etapa de normalização: do texto extraído ao texto que o RAG vai usar.

Lê o que a extração gravou em `data/texto_acervo/` — o `.txt` com as páginas
separadas por `\\f`, o `.json` e o texto posicionado de cada página — e grava ao
lado, sem tocar em nada da extração:

- `<arquivo>.normalizado.txt`, com o **mesmo número de páginas**;
- `<arquivo>.qualidade.json`, com os indicadores e as regras aplicadas em cada
  página, que o relatório de qualidade soma.

A página com texto posicionado é normalizada a partir dele, onde as regiões e o
`¬` do Kraken ainda existem; a revisada (`pagina_NNNN.revisada.xml`, que virá do
eScriptorium) tem precedência sobre a do OCR. A página sem posição (texto
digital, OCR anterior) é normalizada a partir do `.txt`.
"""

import json
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from ..config import ConfigNormalizacao, ConfigQualidade
from ..erros import ErroPreRequisito
from ..modelos import ResultadoEtapa
from ..normalizacao_texto import blocos_da_pagina_posicionada, blocos_do_texto, normalizar_blocos
from ..protocolos import SugeridorDePalavras, VerificadorDePalavras
from ..qualidade_ocr import detectar_idioma, indicadores_da_pagina, nivel_da_pagina
from ..texto_posicionado import PaginaPosicionada, ler_page_xml
from . import RelatorProgresso, sem_progresso

SEPARADOR_DE_PAGINA = "\f"
SUFIXO_NORMALIZADO = ".normalizado.txt"
SUFIXO_QUALIDADE = ".qualidade.json"
# Os mesmos nomes que a extração grava; repetidos aqui porque etapa não importa etapa.
SUFIXO_REVISADO = ".revisada.xml"
SUFIXO_DO_OCR = ".ocr.xml"

# Registro da extração → idioma (código do Tesseract). O serviço lê o campo
# `idioma` e, em extração antiga que não o tem, o catálogo da exportação.
IdiomaDoRegistro = Callable[[dict], str]


def pagina_vigente(pasta_das_paginas: Path, numero: int) -> PaginaPosicionada | None:
    """O texto posicionado da página: o revisado, se houver; senão o do OCR; senão nenhum."""
    for sufixo in (SUFIXO_REVISADO, SUFIXO_DO_OCR):
        arquivo = pasta_das_paginas / f"pagina_{numero:04d}{sufixo}"
        if arquivo.is_file():
            return ler_page_xml(arquivo.read_bytes())
    return None


def _gravar_atomico(destino: Path, conteudo: str) -> None:
    temporario = destino.with_name(destino.name + ".tmp")
    temporario.write_text(conteudo, encoding="utf-8")
    temporario.replace(destino)


def normalizar_documento(
    arquivo_registro: Path,
    idioma: str,
    config: ConfigNormalizacao,
    qualidade: ConfigQualidade,
    ignorar: frozenset[str],
    verificador: VerificadorDePalavras | None,
    sugeridor: SugeridorDePalavras | None,
) -> tuple[str, dict]:
    """Texto normalizado de um PDF e o registro de qualidade dele."""
    registro = json.loads(arquivo_registro.read_text(encoding="utf-8"))
    arquivo = registro["arquivo"]
    pasta = arquivo_registro.parent
    paginas = (pasta / f"{arquivo}.txt").read_text(encoding="utf-8").split(SEPARADOR_DE_PAGINA)
    origens = registro.get("origem_por_pagina") or [registro.get("origem_do_texto", "")] * len(paginas)
    idioma_do_catalogo = idioma
    if not idioma and verificador:
        idioma = detectar_idioma("\n".join(paginas), verificador, qualidade)

    def desconhecidas_de(palavras: list[str]) -> set[str] | None:
        return verificador(palavras, idioma) if verificador else None

    normalizadas, por_pagina = [], []
    for numero, texto in enumerate(paginas, start=1):
        origem = origens[numero - 1] if numero - 1 < len(origens) else ""
        posicionada = pagina_vigente(pasta / f"{arquivo}.paginas", numero)
        if posicionada is not None and posicionada.tem_posicao:
            blocos = blocos_da_pagina_posicionada(posicionada, ignorar)
        else:
            blocos = blocos_do_texto(texto)
        normalizada = normalizar_blocos(blocos, config, desconhecidas_de if verificador else None)
        indicadores = indicadores_da_pagina(
            normalizada.texto, idioma, qualidade, verificador, sugeridor, posicionada, ignorar
        )
        por_pagina.append(
            {
                "pagina": numero,
                "origem": origem,
                "nivel": nivel_da_pagina(indicadores, origem, qualidade),
                **indicadores,
                "regras": normalizada.contagens,
                "exemplos": normalizada.exemplos,
            }
        )
        normalizadas.append(normalizada.texto)

    qualidade_do_documento = {
        "handle": registro.get("handle", ""),
        "pasta_item": registro.get("pasta_item", ""),
        "arquivo": arquivo,
        "idioma": idioma,
        "idioma_detectado": bool(idioma) and not idioma_do_catalogo,
        "total_de_paginas": len(paginas),
        "origem_do_texto": registro.get("origem_do_texto", ""),
        "produtor_do_pdf": registro.get("produtor_do_pdf", ""),
        "ocr_ferramenta": registro.get("ocr_ferramenta", ""),
        "ocr_versao": registro.get("ocr_versao", ""),
        "linhas_por_tipo": registro.get("linhas_por_tipo", {}),
        "comparacao_ocr_anterior": registro.get("comparacao_ocr_anterior", {}),
        "paginas": por_pagina,
        "regras_de_normalizacao": asdict(config),
        "limiares_de_qualidade": asdict(qualidade),
        "normalizado_em": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    return SEPARADOR_DE_PAGINA.join(normalizadas), qualidade_do_documento


def executar(
    pasta_texto: Path,
    config: ConfigNormalizacao,
    qualidade: ConfigQualidade,
    ignorar: frozenset[str],
    idioma_de: IdiomaDoRegistro,
    verificador: VerificadorDePalavras | None = None,
    sugeridor: SugeridorDePalavras | None = None,
    *,
    documentos: list[str] | None = None,
    progresso: RelatorProgresso = sem_progresso,
) -> ResultadoEtapa:
    """Normaliza todo PDF extraído em `pasta_texto`. Barato: refaz sempre, sem OCR."""
    registros = sorted(
        r
        for r in pasta_texto.glob("*/*.json")
        if not r.name.endswith(SUFIXO_QUALIDADE) and r.name.removesuffix(".json").lower().endswith(".pdf")
    )
    if not registros:
        raise ErroPreRequisito(f"Nenhum texto extraído em {pasta_texto}.", "Rode antes: python3 main.py extrair")

    resultado = ResultadoEtapa()
    resultado.detalhes = {"pdfs": 0, "paginas": 0, "pasta": pasta_texto, "avisos": []}
    for indice, arquivo_registro in enumerate(registros, start=1):
        try:
            registro = json.loads(arquivo_registro.read_text(encoding="utf-8"))
            if documentos is not None and registro.get("handle") not in documentos:
                resultado.ignorados += 1
                continue
            idioma = idioma_de(registro)
            texto, qualidade_do_documento = normalizar_documento(
                arquivo_registro, idioma, config, qualidade, ignorar, verificador, sugeridor
            )
            pasta, arquivo = arquivo_registro.parent, registro["arquivo"]
            _gravar_atomico(pasta / f"{arquivo}{SUFIXO_NORMALIZADO}", texto)
            _gravar_atomico(
                pasta / f"{arquivo}{SUFIXO_QUALIDADE}",
                json.dumps(qualidade_do_documento, ensure_ascii=False, indent=2) + "\n",
            )
            resultado.processados += 1
            resultado.detalhes["pdfs"] += 1
            resultado.detalhes["paginas"] += qualidade_do_documento["total_de_paginas"]
            if not qualidade_do_documento["idioma"]:
                resultado.detalhes["avisos"].append(f"{registro.get('handle')}: sem idioma, sem medida do dicionário")
            elif qualidade_do_documento["idioma_detectado"]:
                resultado.detalhes["avisos"].append(
                    f"{registro.get('handle')}: sem idioma no catálogo; detectado {qualidade_do_documento['idioma']}"
                )
        except Exception as erro:
            resultado.falhas.append(f"{arquivo_registro.parent.name} / {arquivo_registro.name}: {erro}")
        progresso(indice, len(registros), arquivo_registro.name)
    return resultado
