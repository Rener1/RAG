"""
Leitura de PDF e OCR, por programas do sistema.

Fica em `clientes/` pelo mesmo motivo do Ollama e do Qdrant: é adaptador de
ferramenta externa. A etapa de extração orquestra; este arquivo chama
processos. Nenhuma dependência Python nova — Poppler, OCRmyPDF e Tesseract são
pacotes do sistema, e é por `subprocess` que se fala com eles.

Duas decisões que não são óbvias:

- `pdftotext` sem `-layout`. Com ele o texto sai na posição da página, e duas
  colunas viram linhas intercaladas; sem ele sai na ordem de leitura.
- OCRmyPDF em vez de Tesseract direto. Ele corrige inclinação e rotação antes
  de reconhecer, paraleliza por página e aceita a lista de páginas a fazer.
  Com `--output-type none` não monta PDF nenhum: só o texto do `--sidecar`.
"""

import os
import re
import subprocess
import tempfile
from dataclasses import replace
from functools import cached_property
from pathlib import Path

from ..config import ConfigExtracao, ConfigKraken
from ..erros import ErroConfiguracao, ErroPipeline
from ..modelos import LeituraDoMotor
from ..texto_posicionado import PaginaPosicionada, ler_page_xml, pagina_sem_posicao

SEPARADOR_DE_PAGINA = "\f"

INSTALACAO = "sudo dnf install ocrmypdf tesseract tesseract-langpack-por tesseract-osd poppler-utils"

# Códigos de saída do OCRmyPDF (ocrmypdf.ExitCode).
SAIDA_DEPENDENCIA_AUSENTE = 3
SAIDA_PDF_CRIPTOGRAFADO = 8


def _rodar(comando: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(comando, capture_output=True, text=True, encoding="utf-8", errors="replace")
    except FileNotFoundError as erro:
        raise ErroConfiguracao(f"`{comando[0]}` não está instalado.", INSTALACAO) from erro


def _final(texto: str, linhas: int = 3) -> str:
    """As últimas linhas de um stderr — é onde a ferramenta diz o que houve."""
    return " | ".join(linha.strip() for linha in texto.strip().splitlines()[-linhas:])


def idiomas_do_tesseract() -> set[str] | None:
    """Os pacotes de idioma instalados, ou `None` quando o Tesseract não está.

    Sem o pacote do idioma pedido o OCR falha; sem o `osd`, a correção de
    rotação. Os dois só aparecem aqui, não na instalação do binário.
    """
    try:
        processo = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True)
    except FileNotFoundError:
        return None
    # A primeira linha é o cabeçalho ("List of available languages ...").
    return {linha.strip() for linha in processo.stdout.splitlines()[1:] if linha.strip()}


class LeitorPoppler:
    """Camada de texto do PDF via `pdfinfo` e `pdftotext`."""

    def contar_paginas(self, caminho: Path) -> int:
        processo = _rodar(["pdfinfo", str(caminho)])
        if processo.returncode != 0:
            raise ErroPipeline(f"pdfinfo não leu {caminho.name}: {_final(processo.stderr)}")
        encontrado = re.search(r"^Pages:\s+(\d+)", processo.stdout, re.MULTILINE)
        if not encontrado:
            raise ErroPipeline(f"pdfinfo não informou o número de páginas de {caminho.name}.")
        return int(encontrado.group(1))

    def textos_das_paginas(self, caminho: Path) -> list[str]:
        total = self.contar_paginas(caminho)
        processo = _rodar(["pdftotext", "-enc", "UTF-8", str(caminho), "-"])
        if processo.returncode != 0:
            raise ErroPipeline(f"pdftotext não leu {caminho.name}: {_final(processo.stderr)}")

        # O pdftotext fecha cada página com `\f`, a última inclusive (conferido
        # no Poppler 26.01): N páginas dão N+1 pedaços, e o último é vazio.
        # Aceitar N pedaços seria tratar uma página perdida como página vazia.
        *pedacos, resto = processo.stdout.split(SEPARADOR_DE_PAGINA)
        if len(pedacos) != total or resto.strip():
            raise ErroPipeline(
                f"{caminho.name}: o pdftotext devolveu {len(pedacos)} páginas, mas o PDF tem {total}. "
                "Gravar assim deslocaria a numeração das páginas."
            )
        return pedacos

    def _areas_das_paginas(self, caminho: Path, total: int) -> dict[int, float]:
        """Área de cada página em pontos², pela `MediaBox` que o `pdfinfo` informa."""
        processo = _rodar(["pdfinfo", "-f", "1", "-l", str(total), str(caminho)])
        areas = {}
        for numero, largura, altura in re.findall(
            r"^Page\s+(\d+) size:\s+([\d.]+) x ([\d.]+)", processo.stdout, re.MULTILINE
        ):
            areas[int(numero)] = float(largura) * float(altura)
        return areas

    def coberturas_de_imagem(self, caminho: Path) -> list[float]:
        total = self.contar_paginas(caminho)
        areas = self._areas_das_paginas(caminho, total)
        coberturas = [0.0] * total
        processo = _rodar(["pdfimages", "-list", str(caminho)])
        if processo.returncode != 0:
            return coberturas
        # page num type width height color comp bpc enc interp object ID x-ppi y-ppi size ratio
        # O "object ID" são dois campos ("61 0"), ou um só para imagem embutida ("[inline]").
        for linha in processo.stdout.splitlines()[2:]:
            campos = linha.split()
            if len(campos) < 13 or campos[2] != "image" or not campos[0].isdigit():
                continue
            inicio_ppi = 11 if campos[10].startswith("[") else 12
            try:
                pagina, largura, altura = int(campos[0]), int(campos[3]), int(campos[4])
                x_ppi, y_ppi = float(campos[inicio_ppi]), float(campos[inicio_ppi + 1])
            except (ValueError, IndexError):
                continue
            area = areas.get(pagina)
            if not area or x_ppi <= 0 or y_ppi <= 0 or not 1 <= pagina <= total:
                continue
            # pixels ÷ ppi = polegadas; × 72 = pontos, a unidade da página
            coberta = (largura / x_ppi * 72) * (altura / y_ppi * 72) / area
            coberturas[pagina - 1] = max(coberturas[pagina - 1], coberta)
        return coberturas

    def produtor(self, caminho: Path) -> str:
        processo = _rodar(["pdfinfo", str(caminho)])
        campos = re.findall(r"^(Creator|Producer):\s+(.+)$", processo.stdout, re.MULTILINE)
        return "; ".join(f"{nome}: {valor.strip()}" for nome, valor in campos)


class ReconhecedorOcrmypdf:
    """OCR das páginas pedidas, via OCRmyPDF com Tesseract."""

    def __init__(self, config: ConfigExtracao) -> None:
        self._config = config

    @property
    def _processos(self) -> int:
        return self._config.processos or os.cpu_count() or 1

    @property
    def _parametros(self) -> list[str]:
        """Os parâmetros que mudam o resultado — os que se gravam com cada documento."""
        return ["-l", self._config.idioma, "--force-ocr", "--deskew", "--rotate-pages"]

    @cached_property
    def identificacao(self) -> dict[str, str]:
        # Sob demanda e uma vez só: um acervo todo digital não precisa ter o
        # OCR instalado, e a versão não muda no meio de uma execução.
        ocrmypdf = _rodar(["ocrmypdf", "--version"])
        tesseract = _rodar(["tesseract", "--version"])
        # O Tesseract 4 escreve a versão no stderr; o 5, no stdout.
        versao_tesseract = (tesseract.stdout or tesseract.stderr).strip().splitlines()[0]
        return {
            "ferramenta": "ocrmypdf + tesseract",
            "versao": f"ocrmypdf {ocrmypdf.stdout.strip()}; {versao_tesseract}",
            "parametros": " ".join(self._parametros),
        }

    def reconhecer(self, caminho: Path, paginas: list[int]) -> dict[int, PaginaPosicionada]:
        """Só texto: o sidecar do OCRmyPDF não traz coordenadas."""
        return {n: pagina_sem_posicao(t) for n, t in self.reconhecer_texto(caminho, paginas).items()}

    def reconhecer_texto(self, caminho: Path, paginas: list[int]) -> dict[int, str]:
        if not paginas:
            return {}

        with tempfile.TemporaryDirectory(prefix="rag-ocr-") as pasta:
            sidecar = Path(pasta) / "texto.txt"
            comando = [
                "ocrmypdf",
                *self._parametros,
                "--pages",
                ",".join(str(n) for n in paginas),
                "--jobs",
                str(self._processos),
                "--quiet",
                "--sidecar",
                str(sidecar),
                "--output-type",
                "none",
                str(caminho),
                "-",
            ]
            processo = _rodar(comando)

            if processo.returncode == SAIDA_DEPENDENCIA_AUSENTE:
                raise ErroConfiguracao(f"O OCRmyPDF não achou uma dependência: {_final(processo.stderr)}", INSTALACAO)
            if processo.returncode == SAIDA_PDF_CRIPTOGRAFADO:
                raise ErroPipeline(f"{caminho.name} é criptografado — o OCR não abre.")
            if processo.returncode != 0:
                raise ErroPipeline(
                    f"O OCRmyPDF saiu com código {processo.returncode} em {caminho.name}: {_final(processo.stderr)}"
                )

            texto = sidecar.read_text(encoding="utf-8")

        return paginas_do_sidecar(texto, paginas, caminho.name)


# Aviso que o OCRmyPDF põe no sidecar no lugar das páginas não pedidas. O 16.7
# escreve "page(s) 2-3", e páginas puladas em sequência viram UM pedaço só.
PADRAO_PAGINA_PULADA = re.compile(r"\s*\[OCR skipped on page(?:\(s\))?s? (\d+)(?:\s*-\s*(\d+))?\]\s*")


def paginas_do_sidecar(texto: str, pedidas: list[int], nome: str) -> dict[int, str]:
    """Texto de cada página pedida, a partir do sidecar do OCRmyPDF.

    O sidecar separa os pedaços com `\\f`, mas um pedaço não é uma página:
    páginas puladas em sequência saem num aviso só (conferido no OCRmyPDF
    16.7), então indexar por posição pega a página errada sem erro nenhum. A
    numeração é reconstruída pelos avisos, que dizem que páginas cobrem, e
    qualquer descompasso é erro — nunca texto atribuído à página errada.
    """
    textos: dict[int, str] = {}
    atual = 1
    for pedaco in texto.split(SEPARADOR_DE_PAGINA):
        pulada = PADRAO_PAGINA_PULADA.fullmatch(pedaco)
        if not pulada:
            textos[atual] = pedaco
            atual += 1
            continue
        inicio, fim = int(pulada.group(1)), int(pulada.group(2) or pulada.group(1))
        if inicio != atual or fim < inicio:
            raise ErroPipeline(f"{nome}: o OCR pulou as páginas {inicio}–{fim} quando se esperava a {atual}.")
        atual = fim + 1

    faltam = [n for n in pedidas if n not in textos]
    if faltam:
        raise ErroPipeline(f"{nome}: o OCR não devolveu as páginas {faltam}.")
    return {n: textos[n] for n in pedidas}


# ── motores para a avaliação do OCR ───────────────────────────────────────
#
# Cada motor lê uma página e devolve o texto, para ser comparado com uma
# transcrição de referência (`rag.avaliacao_ocr`). Não substituem a extração:
# são as variantes que a medição compara antes de qualquer uma virar padrão.

# Valores de `thresholding_method` do Tesseract 5: 0 é o Otsu global de sempre,
# 2 é o Sauvola, adaptativo por região — o que recuperou o P1 do registro.
BINARIZACOES = {"otsu": 0, "sauvola": 2}


class MotorOcrmypdf:
    """O caminho da extração atual (OCRmyPDF + Tesseract), uma página de cada vez."""

    def __init__(self, config: ConfigExtracao) -> None:
        self._config = config

    def __call__(self, pdf: Path, pagina: int, idioma: str) -> LeituraDoMotor:
        reconhecedor = ReconhecedorOcrmypdf(replace(self._config, idioma=idioma))
        return LeituraDoMotor(reconhecedor.reconhecer_texto(pdf, [pagina])[pagina])


class MotorTesseract:
    """Tesseract direto sobre a página rasterizada, com binarização e limpeza escolhidas.

    Sem correção de orientação: as páginas de teste estão em pé, e uma rotação
    errada seria um erro que não é do motor.
    """

    def __init__(self, binarizacao: str = "otsu", limpar: bool = False, dpi: int = 300) -> None:
        self._binarizacao = BINARIZACOES[binarizacao]
        self._limpar = limpar
        self._dpi = dpi

    def __call__(self, pdf: Path, pagina: int, idioma: str) -> LeituraDoMotor:
        with tempfile.TemporaryDirectory(prefix="rag-ocr-") as pasta:
            raiz = Path(pasta) / "pagina"
            processo = _rodar(
                [
                    "pdftoppm",
                    "-r",
                    str(self._dpi),
                    "-gray",
                    "-f",
                    str(pagina),
                    "-l",
                    str(pagina),
                    "-singlefile",
                    str(pdf),
                    str(raiz),
                ]
            )
            imagem = raiz.with_suffix(".pgm")
            if processo.returncode != 0 or not imagem.is_file():
                raise ErroPipeline(
                    f"pdftoppm não rasterizou a página {pagina} de {pdf.name}: {_final(processo.stderr)}"
                )

            if self._limpar:
                limpa = Path(pasta) / "limpa.pgm"
                processo = _rodar(["unpaper", "--overwrite", str(imagem), str(limpa)])
                if processo.returncode != 0:
                    raise ErroPipeline(f"unpaper falhou na página {pagina} de {pdf.name}: {_final(processo.stderr)}")
                imagem = limpa

            saida = Path(pasta) / "saida"
            processo = _rodar(
                [
                    "tesseract",
                    str(imagem),
                    str(saida),
                    "-l",
                    idioma,
                    "-c",
                    f"thresholding_method={self._binarizacao}",
                    "txt",
                    "tsv",
                ]
            )
            if processo.returncode != 0:
                raise ErroConfiguracao(f"O Tesseract falhou: {_final(processo.stderr)}", INSTALACAO)
            texto = saida.with_suffix(".txt").read_text(encoding="utf-8")
            confianca = confianca_media_do_tsv(saida.with_suffix(".tsv").read_text(encoding="utf-8"))
        return LeituraDoMotor(texto, confianca)


def _rasterizar_png(pdf: Path, pagina: int, destino: Path, dpi: int) -> None:
    """Página em PNG de tons de cinza, em `destino` (sem extensão: o pdftoppm a põe)."""
    processo = _rodar(
        ["pdftoppm", "-r", str(dpi), "-gray", "-png", "-f", str(pagina), "-l", str(pagina), "-singlefile", str(pdf), str(destino)]
    )  # fmt: skip
    if processo.returncode != 0:
        raise ErroPipeline(f"pdftoppm não rasterizou a página {pagina} de {pdf.name}: {_final(processo.stderr)}")


def _exigir_modelo(config: ConfigKraken, pasta_modelos: Path) -> None:
    """Antes de rasterizar: sem o modelo, nada do que vem depois serve."""
    if not (pasta_modelos / config.modelo).is_file():
        raise ErroConfiguracao(
            f"Modelo do Kraken não encontrado em {pasta_modelos / config.modelo}.",
            f"podman run --rm -v {pasta_modelos}:/modelos:Z {config.imagem} get 10.5281/zenodo.10592716",
        )


def _rodar_kraken(
    config: ConfigKraken, pasta_modelos: Path, pasta: Path, pares: list[tuple[str, str]], formato: list[str]
) -> None:
    """Uma execução do container sobre `pasta`, com um par entrada → saída por página.

    O modelo é carregado uma vez por execução, e é por isso que o reconhecedor
    manda várias páginas de uma vez.
    """
    entradas = [argumento for entrada, saida in pares for argumento in ("-i", entrada, saida)]
    processo = _rodar(
        [
            "podman", "run", "--rm", "--pull=never",
            "-v", f"{pasta_modelos}:/modelos:ro,Z",
            "-v", f"{pasta}:/trabalho:Z",
            config.imagem,
            *formato, *entradas, "segment", "-bl", "ocr", "-m", f"/modelos/{config.modelo}",
        ]
    )  # fmt: skip
    if processo.returncode != 0 or not all((pasta / saida).is_file() for _, saida in pares):
        if "image not known" in processo.stderr or "no such image" in processo.stderr.lower():
            raise ErroConfiguracao(
                f"A imagem {config.imagem} não existe.",
                "podman build -t rag-kraken -f Containerfile.kraken .",
            )
        raise ErroPipeline(f"O Kraken falhou: {_final(processo.stderr)}")


class MotorKraken:
    """Kraken no container `rag-kraken`: segmentação por linha de base e reconhecimento.

    A página é rasterizada aqui, com o mesmo `pdftoppm` do Tesseract, para a
    comparação ser justa; o container só lê a imagem. O idioma não entra: o
    modelo é multilíngue e reconhece por caractere, sem dicionário. Devolve o
    texto puro do Kraken, sem regra de região — é a linha de base da medição.
    """

    def __init__(self, config: ConfigKraken, pasta_modelos: Path, dpi: int = 300) -> None:
        self._config = config
        self._pasta_modelos = pasta_modelos
        self._dpi = dpi

    def __call__(self, pdf: Path, pagina: int, idioma: str) -> LeituraDoMotor:
        _exigir_modelo(self._config, self._pasta_modelos)
        with tempfile.TemporaryDirectory(prefix="rag-kraken-") as pasta:
            _rasterizar_png(pdf, pagina, Path(pasta) / "pagina", self._dpi)
            try:
                _rodar_kraken(self._config, self._pasta_modelos, Path(pasta), [("pagina.png", "pagina.txt")], [])
            except ErroConfiguracao:
                raise
            except ErroPipeline as erro:
                raise ErroPipeline(f"Página {pagina} de {pdf.name}: {erro}") from erro
            texto = (Path(pasta) / "pagina.txt").read_text(encoding="utf-8")
        # O CATMuS marca o hífen de fim de linha com `¬`, convenção de transcrição
        # e não leitura: sem a troca, a avaliação puniria a convenção como erro.
        return LeituraDoMotor(texto.replace("¬", "-"))


class ReconhecedorKraken:
    """OCR da extração pelo Kraken, com texto posicionado (PAGE XML) por página.

    Manda as páginas em lotes de `paginas_por_chamada`: cada execução do
    container carrega o modelo uma vez, e as imagens do lote ficam no /tmp.
    """

    def __init__(self, config: ConfigKraken, pasta_modelos: Path) -> None:
        self._config = config
        self._pasta_modelos = pasta_modelos

    @cached_property
    def identificacao(self) -> dict[str, str]:
        processo = _rodar(["podman", "run", "--rm", "--pull=never", self._config.imagem, "--version"])
        versao = (
            processo.stdout.strip().splitlines()[-1] if processo.returncode == 0 and processo.stdout.strip() else ""
        )
        return {
            "ferramenta": "kraken",
            "versao": f"{versao or 'kraken (versão não lida)'}; modelo {Path(self._config.modelo).name}",
            "parametros": f"pdftoppm -r {self._config.dpi} -gray; segment -bl; ocr -m {self._config.modelo}",
        }

    def reconhecer(self, caminho: Path, paginas: list[int]) -> dict[int, PaginaPosicionada]:
        _exigir_modelo(self._config, self._pasta_modelos)
        tamanho = max(1, self._config.paginas_por_chamada)
        resultado: dict[int, PaginaPosicionada] = {}
        for inicio in range(0, len(paginas), tamanho):
            resultado |= self._reconhecer_lote(caminho, paginas[inicio : inicio + tamanho])
        return resultado

    def _reconhecer_lote(self, caminho: Path, paginas: list[int]) -> dict[int, PaginaPosicionada]:
        with tempfile.TemporaryDirectory(prefix="rag-kraken-") as nome:
            pasta = Path(nome)
            pares = []
            for numero in paginas:
                _rasterizar_png(caminho, numero, pasta / f"pagina_{numero:04d}", self._config.dpi)
                pares.append((f"pagina_{numero:04d}.png", f"pagina_{numero:04d}.xml"))
            try:
                _rodar_kraken(self._config, self._pasta_modelos, pasta, pares, ["-x"])
            except ErroConfiguracao:
                raise
            except ErroPipeline as erro:
                raise ErroPipeline(f"{caminho.name}, páginas {paginas[0]}–{paginas[-1]}: {erro}") from erro
            return {n: ler_page_xml((pasta / saida).read_bytes()) for n, (_, saida) in zip(paginas, pares, strict=True)}


def confianca_media_do_tsv(tsv: str) -> float | None:
    """Média da confiança das palavras (nível 5) com texto. `None` se não houver nenhuma."""
    valores = []
    for linha in tsv.splitlines()[1:]:
        campos = linha.split("\t")
        if len(campos) == 12 and campos[0] == "5" and campos[11].strip():
            try:
                valores.append(float(campos[10]))
            except ValueError:
                continue
    valores = [v for v in valores if v >= 0]
    return sum(valores) / len(valores) if valores else None
