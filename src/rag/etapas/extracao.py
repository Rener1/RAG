"""
Extração do texto dos PDFs do acervo, com OCR só onde falta texto.

Lê a exportação do DSpace em pastas por item (Simple Archive Format) e grava,
para cada PDF, o texto em `data/texto_acervo/<handle>/<arquivo>.txt` e o
registro da extração num `.json` ao lado. Página que passou por OCR com
coordenadas ganha também o texto posicionado, em
`<arquivo>.paginas/pagina_NNNN.ocr.xml`: é o mestre, e a linha da página no
`.txt` é derivada dele, sem as regiões de carimbo e ruído.

Não se gera PDF novo. O pipeline só consome texto, e a citação aponta para o
PDF original no repositório, pelo handle — um PDF pesquisável nosso ficaria em
disco sem ninguém abrir.

A decisão é por página, não por documento: a camada de texto existente é lida
primeiro, e só a página abaixo do mínimo de caracteres vai ao OCR. É o que
trata o PDF misto (capa digitalizada, miolo digital) sem refazer o que já
estava bom.

O `.txt` separa as páginas com `\\f`, a convenção do `pdftotext`: a página N é
o N-ésimo pedaço de `texto.split("\\f")`. Essa divisão é o que torna a citação
por página possível (`fase-1` §4.3) — não pode ser normalizada fora.
"""

import hashlib
import json
import os
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from ..config import ConfigExtracao, ConfigRegioes
from ..erros import ErroConfiguracao, ErroPreRequisito
from ..modelos import ResultadoEtapa
from ..protocolos import LeitorDePdf, ReconhecedorOptico, VerificadorDePalavras
from ..qualidade_ocr import fracao_fora_do_dicionario
from ..texto_posicionado import (
    PaginaPosicionada,
    classificar_regioes,
    escrever_page_xml,
    texto_da_pagina,
    tipos_ignorados,
)
from . import RelatorProgresso, sem_progresso

SEPARADOR_DE_PAGINA = "\f"

# Sufixo do texto posicionado que o OCR produz. O revisado, que virá do
# eScriptorium, terá outro sufixo, e a re-extração nunca o apaga.
SUFIXO_DO_OCR = ".ocr.xml"
# Texto de um OCR anterior (camada que o PDF já trazia sobre a página
# escaneada), guardado ao lado para a auditoria da escolha.
SUFIXO_DO_ANTERIOR = ".anterior.txt"

# De onde veio o texto de cada página, no registro (`origem_por_pagina`).
ORIGEM_DIGITAL = "digital_nativo"
ORIGEM_OCR_ANTERIOR = "ocr_anterior"
ORIGEM_OCR = "ocr"
ORIGEM_SEM_TEXTO = "sem_texto"

# Bundle em que o DSpace guarda o arquivo depositado. Os outros são derivados
# dele (TEXT é o texto que o próprio DSpace extraiu, THUMBNAIL a miniatura) ou
# não são conteúdo (LICENSE). Linha do `contents` sem bundle é ORIGINAL.
BUNDLE_ORIGINAL = "ORIGINAL"


@dataclass(frozen=True)
class PdfDoAcervo:
    """Um PDF de um item da exportação."""

    handle: str
    pasta_item: str
    arquivo: str
    caminho: Path
    idioma: str = ""  # código do Tesseract tirado do catálogo; vazio quando o catálogo não diz


# `dc.language.iso` do DSpace → pacote de idioma do Tesseract. O acervo grava
# `pt`, `en_US`, `es`, `fr` e `other`; o que não está aqui fica vazio, e quem
# usa decide o padrão.
IDIOMAS_DO_TESSERACT = {"pt": "por", "es": "spa", "en": "eng", "fr": "fra", "de": "deu", "it": "ita"}


def idioma_do_tesseract(iso: str) -> str:
    """`pt`, `pt_BR`, `en-US` → `por`, `por`, `eng`. Desconhecido ou `other` → vazio."""
    return IDIOMAS_DO_TESSERACT.get(iso.strip().lower().replace("-", "_").split("_")[0], "")


def idioma_do_item(pasta: Path) -> str:
    """Idioma do item pelo `dublin_core.xml` da exportação. Vazio se não houver ou não for legível."""
    try:
        raiz = ET.parse(pasta / "dublin_core.xml").getroot()
    except (OSError, ET.ParseError):
        return ""
    for valor in raiz.iter("dcvalue"):
        if valor.get("element") == "language" and valor.text:
            idioma = idioma_do_tesseract(valor.text)
            if idioma:
                return idioma
    return ""


def titulo_do_item(pasta: Path) -> str:
    """`dc.title` do item, pelo `dublin_core.xml`. Vazio se não houver."""
    try:
        raiz = ET.parse(pasta / "dublin_core.xml").getroot()
    except (OSError, ET.ParseError):
        return ""
    for valor in raiz.iter("dcvalue"):
        if valor.get("element") == "title" and valor.get("qualifier") in (None, "", "none") and valor.text:
            return valor.text.strip()
    return ""


def nome_seguro(handle: str) -> str:
    """Handle → nome de pasta. `123456789/42` vira `123456789_42`."""
    return handle.strip().replace("/", "_")


def _caracteres_uteis(texto: str) -> int:
    return sum(1 for caractere in texto if caractere.isalnum())


def pagina_tem_texto(texto: str, minimo: int) -> bool:
    """Conta só letras e dígitos: número de página solto e lixo de camada não contam."""
    return _caracteres_uteis(texto) >= minimo


def _arquivos_originais(contents: str) -> list[str]:
    """Nomes do bundle ORIGINAL listados no `contents` de um item.

    Cada linha é o nome do arquivo seguido de campos separados por tabulação
    (`bundle:`, `permissions:`, `primary:`...). Nome com barra ou `..` é
    descartado: o arquivo tem de estar na própria pasta do item.
    """
    nomes = []
    for linha in contents.splitlines():
        if not linha.strip():
            continue
        nome, *campos = linha.split("\t")
        bundle = next((c.removeprefix("bundle:") for c in campos if c.startswith("bundle:")), BUNDLE_ORIGINAL)
        if bundle == BUNDLE_ORIGINAL and nome == Path(nome).name and nome not in {".", ".."}:
            nomes.append(nome)
    return nomes


def listar_pdfs(pasta_exportacao: Path) -> tuple[list[PdfDoAcervo], list[str]]:
    """Os PDFs da exportação, em ordem estável, e os avisos sobre o que ficou de fora.

    Item sem `handle` usa o nome da pasta no lugar — continua rastreável na
    exportação, e o aviso diz qual é.
    """
    pdfs: list[PdfDoAcervo] = []
    avisos: list[str] = []

    for pasta in sorted(p for p in pasta_exportacao.iterdir() if p.is_dir()):
        contents = pasta / "contents"
        if not contents.is_file():
            avisos.append(f"{pasta.name}: sem arquivo `contents`, ignorada")
            continue

        arquivo_handle = pasta / "handle"
        if arquivo_handle.is_file():
            handle = arquivo_handle.read_text(encoding="utf-8").strip()
        else:
            handle = pasta.name
            avisos.append(f"{pasta.name}: sem arquivo `handle`, identificada pelo nome da pasta")

        for nome in _arquivos_originais(contents.read_text(encoding="utf-8")):
            if not nome.lower().endswith(".pdf"):
                continue
            caminho = pasta / nome
            if not caminho.is_file():
                avisos.append(f"{pasta.name}: `{nome}` está no contents mas não na pasta")
                continue
            pdfs.append(
                PdfDoAcervo(
                    handle=handle,
                    pasta_item=pasta.name,
                    arquivo=nome,
                    caminho=caminho,
                    idioma=idioma_do_item(pasta),
                )
            )

    return pdfs, avisos


def sha256_do_arquivo(caminho: Path) -> str:
    resumo = hashlib.sha256()
    with caminho.open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1 << 20), b""):
            resumo.update(bloco)
    return resumo.hexdigest()


def normalizar_pagina(texto: str) -> str:
    """NFC e sem `\\f` interno — um `\\f` a mais deslocaria todas as páginas seguintes."""
    return unicodedata.normalize("NFC", texto).replace(SEPARADOR_DE_PAGINA, "\n").strip()


def _gravar_atomico(destino: Path, conteudo: str) -> None:
    temporario = destino.with_name(destino.name + ".tmp")
    temporario.write_text(conteudo, encoding="utf-8")
    os.replace(temporario, destino)


def _ja_extraido(registro: Path, sha256: str) -> bool:
    try:
        return json.loads(registro.read_text(encoding="utf-8")).get("sha256_original") == sha256
    except (OSError, ValueError):
        return False


def extrair_pdf(
    pdf: PdfDoAcervo,
    config: ConfigExtracao,
    leitor: LeitorDePdf,
    reconhecedor: ReconhecedorOptico,
    sha256: str,
    regioes: ConfigRegioes | None = None,
    verificador: VerificadorDePalavras | None = None,
) -> tuple[str, dict, dict[int, PaginaPosicionada], dict[int, str]]:
    """Texto de um PDF, com as páginas separadas por `\\f`, o registro, o texto posicionado e os OCRs anteriores.

    O texto posicionado volta só das páginas que ficaram com o nosso OCR e têm
    coordenadas, já com as regras de região aplicadas. Os OCRs anteriores são a
    camada de texto que o PDF trazia sobre página escaneada, por número.
    """
    regioes = regioes or ConfigRegioes()
    ignorar = tipos_ignorados(regioes)
    paginas = [normalizar_pagina(t) for t in leitor.textos_das_paginas(pdf.caminho)]
    sem_texto = [
        n
        for n, texto in enumerate(paginas, start=1)
        if not pagina_tem_texto(texto, config.minimo_de_caracteres_por_pagina)
    ]
    # Texto sobre página escaneada não é texto original: alguém o reconheceu
    # antes (no acervo, o Acrobat 9 no 7891/4657). Vai ao nosso OCR também, e
    # fica a leitura com menos palavras fora do dicionário.
    coberturas = leitor.coberturas_de_imagem(pdf.caminho)
    anteriores = {
        n: paginas[n - 1]
        for n, cobertura in enumerate(coberturas, start=1)
        if cobertura >= config.cobertura_de_pagina_escaneada and n not in sem_texto
    }

    # Página abaixo do mínimo vai ao OCR, mas o OCR só fica se trouxer mais
    # texto. Folha de rosto e abertura de capítulo são curtas e digitais: o
    # OCR as reconheceria do zero, e trocaria texto exato por texto provável.
    paginas_ocr: list[int] = []
    posicionadas: dict[int, PaginaPosicionada] = {}
    comparacao: dict[str, dict] = {}
    para_ocr = sorted(set(sem_texto) | set(anteriores))
    if para_ocr:
        reconhecidas = reconhecedor.reconhecer(pdf.caminho, para_ocr)
        for numero in para_ocr:
            pagina = reconhecidas.get(numero)
            if pagina is None:
                continue
            if pagina.tem_posicao:
                pagina = classificar_regioes(pagina, regioes)
            reconhecida = normalizar_pagina(texto_da_pagina(pagina, ignorar))
            if numero in anteriores:
                fica_o_nosso, comparacao[str(numero)] = _escolher_leitura(
                    anteriores[numero], reconhecida, pdf.idioma, verificador, config
                )
            else:
                fica_o_nosso = _caracteres_uteis(reconhecida) > _caracteres_uteis(paginas[numero - 1])
            if fica_o_nosso:
                paginas[numero - 1] = reconhecida
                paginas_ocr.append(numero)
                if pagina.tem_posicao:
                    posicionadas[numero] = pagina

    registro: dict = {
        "handle": pdf.handle,
        "pasta_item": pdf.pasta_item,
        "arquivo": pdf.arquivo,
        "sha256_original": sha256,
        "total_de_paginas": len(paginas),
        "origem_do_texto": _origem_do_documento(paginas_ocr, anteriores),
        "minimo_de_caracteres_por_pagina": config.minimo_de_caracteres_por_pagina,
        "extraido_em": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    # Os campos de OCR só existem para o que nós processamos (esquema §4.5):
    # de PDF que chegou com texto não se sabe quem gerou a camada.
    if paginas_ocr:
        identificacao = reconhecedor.identificacao
        registro["paginas_ocr"] = paginas_ocr
        registro["ocr_ferramenta"] = identificacao.get("ferramenta", "")
        registro["ocr_versao"] = identificacao.get("versao", "")
        registro["ocr_parametros"] = identificacao.get("parametros", "")
    if pdf.idioma:
        registro["idioma"] = pdf.idioma
    produtor = leitor.produtor(pdf.caminho)
    if produtor:
        registro["produtor_do_pdf"] = produtor
    if anteriores:
        registro["comparacao_ocr_anterior"] = comparacao
    if paginas_ocr or anteriores:
        registro["origem_por_pagina"] = [
            _origem_da_pagina(n, texto, paginas_ocr, anteriores, config) for n, texto in enumerate(paginas, start=1)
        ]
    if posicionadas:
        # As regras entram no registro porque mudam o `.txt`: com outras, o
        # mesmo PAGE XML daria outro texto.
        registro["paginas_posicionadas"] = sorted(posicionadas)
        registro["linhas_por_tipo"] = _somar_contagens(p.contagem_por_tipo() for p in posicionadas.values())
        registro["regras_de_regiao"] = asdict(regioes)

    # Abaixo do mínimo mesmo depois do OCR: página em branco, página curta de
    # verdade, ou imagem que o OCR não leu. Só um olho humano distingue as
    # três, e é para isso que a lista vai ao registro.
    vazias = [
        n
        for n, texto in enumerate(paginas, start=1)
        if not pagina_tem_texto(texto, config.minimo_de_caracteres_por_pagina)
    ]
    if vazias:
        registro["paginas_abaixo_do_minimo"] = vazias

    return SEPARADOR_DE_PAGINA.join(paginas), registro, posicionadas, anteriores


def _escolher_leitura(
    anterior: str, nossa: str, idioma: str, verificador: VerificadorDePalavras | None, config: ConfigExtracao
) -> tuple[bool, dict]:
    """Entre o OCR anterior e o nosso, fica o com menor fração fora do dicionário.

    Sem como medir (sem dicionário do idioma), fica o nosso: um motor só no
    acervo, com regiões e confiança. Leitura nossa abaixo do mínimo não ganha,
    porque trocaria texto por página vazia.
    """
    fracao_anterior = fracao_fora_do_dicionario(anterior, idioma, verificador)
    fracao_nossa = fracao_fora_do_dicionario(nossa, idioma, verificador)
    if not pagina_tem_texto(nossa, config.minimo_de_caracteres_por_pagina):
        fica_o_nosso = False
    elif fracao_anterior is None or fracao_nossa is None:
        fica_o_nosso = True
    else:
        fica_o_nosso = fracao_nossa <= fracao_anterior
    escolhido = ORIGEM_OCR if fica_o_nosso else ORIGEM_OCR_ANTERIOR
    return fica_o_nosso, {"anterior": fracao_anterior, "ocr": fracao_nossa, "escolhido": escolhido}


def _origem_da_pagina(
    numero: int, texto: str, paginas_ocr: list[int], anteriores: dict[int, str], config: ConfigExtracao
) -> str:
    if numero in paginas_ocr:
        return ORIGEM_OCR
    if not pagina_tem_texto(texto, config.minimo_de_caracteres_por_pagina):
        return ORIGEM_SEM_TEXTO
    return ORIGEM_OCR_ANTERIOR if numero in anteriores else ORIGEM_DIGITAL


def _origem_do_documento(paginas_ocr: list[int], anteriores: dict[int, str]) -> str:
    """`ocr` se alguma página é nossa; `ocr_anterior` se só sobrou OCR de outro; senão `digital_nativo`."""
    if paginas_ocr:
        return ORIGEM_OCR
    return ORIGEM_OCR_ANTERIOR if anteriores else ORIGEM_DIGITAL


def _somar_contagens(contagens) -> dict[str, int]:
    total: dict[str, int] = {}
    for contagem in contagens:
        for tipo, linhas in contagem.items():
            total[tipo] = total.get(tipo, 0) + linhas
    return dict(sorted(total.items()))


def pasta_das_paginas(destino: Path, arquivo: str) -> Path:
    return destino / f"{arquivo}.paginas"


def _gravar_paginas(
    pasta: Path, posicionadas: dict[int, PaginaPosicionada], anteriores: dict[int, str], criador: str
) -> None:
    """Troca o texto posicionado do OCR e os OCRs anteriores pelos novos. O revisado fica."""
    if pasta.is_dir():
        for sufixo in (SUFIXO_DO_OCR, SUFIXO_DO_ANTERIOR):
            for antigo in pasta.glob(f"*{sufixo}"):
                antigo.unlink()
    if posicionadas or anteriores:
        pasta.mkdir(parents=True, exist_ok=True)
    for numero, pagina in sorted(posicionadas.items()):
        _gravar_atomico(pasta / f"pagina_{numero:04d}{SUFIXO_DO_OCR}", escrever_page_xml(pagina, criador))
    for numero, texto in sorted(anteriores.items()):
        _gravar_atomico(pasta / f"pagina_{numero:04d}{SUFIXO_DO_ANTERIOR}", texto)


def executar(
    config: ConfigExtracao,
    pasta_exportacao: Path,
    pasta_saida: Path,
    leitor: LeitorDePdf,
    reconhecedor: ReconhecedorOptico,
    *,
    refazer: bool = False,
    documentos: list[str] | None = None,
    regioes: ConfigRegioes | None = None,
    verificador: VerificadorDePalavras | None = None,
    progresso: RelatorProgresso = sem_progresso,
) -> ResultadoEtapa:
    """Extrai todos os PDFs da exportação. Seguro de repetir: pula o que já foi extraído.

    "Já extraído" é ter o `.json` com o mesmo sha256 do original — trocar o PDF
    na exportação basta para ele ser refeito. `documentos` restringe a alguns
    handles e sempre os refaz: é o reprocessamento por documento que a revisão
    amostral pede (`fase-1` §4.2), sem tocar no resto.
    """
    if not pasta_exportacao.is_dir():
        raise ErroPreRequisito(
            f"Exportação do acervo não encontrada em {pasta_exportacao}.",
            "Copie a exportação do DSpace (uma pasta por item) para lá, ou indique outra com --exportacao.",
        )

    pdfs, avisos = listar_pdfs(pasta_exportacao)
    if documentos is not None:
        pedidos = set(documentos)
        avisos += [f"handle {h} não está na exportação" for h in sorted(pedidos - {p.handle for p in pdfs})]
        pdfs = [p for p in pdfs if p.handle in pedidos]
        refazer = True
    elif not pdfs:
        raise ErroPreRequisito(
            f"Nenhum PDF encontrado em {pasta_exportacao}.",
            "A pasta precisa ter uma subpasta por item, cada uma com `contents` e os arquivos — o formato de exportação do DSpace.",
        )

    resultado = ResultadoEtapa()
    resultado.detalhes = {
        "pdfs": len(pdfs),
        "avisos": avisos,
        ORIGEM_DIGITAL: 0,
        ORIGEM_OCR: 0,
        ORIGEM_OCR_ANTERIOR: 0,
        "paginas_ocr": 0,
        "paginas_abaixo_do_minimo": 0,
        "paginas_posicionadas": 0,
        "pasta": pasta_saida,
    }

    for indice, pdf in enumerate(pdfs, start=1):
        destino = pasta_saida / nome_seguro(pdf.handle)
        arquivo_texto = destino / f"{pdf.arquivo}.txt"
        arquivo_registro = destino / f"{pdf.arquivo}.json"

        try:
            sha256 = sha256_do_arquivo(pdf.caminho)
            if not refazer and arquivo_texto.is_file() and _ja_extraido(arquivo_registro, sha256):
                resultado.ignorados += 1
            else:
                texto, registro, posicionadas, anteriores = extrair_pdf(
                    pdf, config, leitor, reconhecedor, sha256, regioes, verificador
                )
                destino.mkdir(parents=True, exist_ok=True)
                # O registro vai por último: é ele que marca o documento como
                # pronto, então uma interrupção antes dele refaz o documento.
                _gravar_paginas(
                    pasta_das_paginas(destino, pdf.arquivo),
                    posicionadas,
                    anteriores,
                    registro.get("ocr_ferramenta", "rag"),
                )
                _gravar_atomico(arquivo_texto, texto)
                _gravar_atomico(arquivo_registro, json.dumps(registro, ensure_ascii=False, indent=2) + "\n")

                resultado.processados += 1
                resultado.detalhes[registro["origem_do_texto"]] += 1
                resultado.detalhes["paginas_ocr"] += len(registro.get("paginas_ocr", []))
                resultado.detalhes["paginas_abaixo_do_minimo"] += len(registro.get("paginas_abaixo_do_minimo", []))
                resultado.detalhes["paginas_posicionadas"] += len(registro.get("paginas_posicionadas", []))
        except ErroConfiguracao:
            # Falta o OCR ou o idioma: falharia igual em todos os documentos.
            raise
        except Exception as erro:
            resultado.falhas.append(f"{pdf.handle} / {pdf.arquivo}: {erro}")

        progresso(indice, len(pdfs), pdf.arquivo)

    return resultado
