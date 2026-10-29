"""
Avaliação do OCR — taxa de erro contra transcrição de referência.

Mede o que nenhum indicador automático mede sozinho: quanto do texto de uma
página o motor de OCR acertou, comparado com uma transcrição conferida por uma
pessoa. É o instrumento que decide se um motor novo (outra binarização, o
Kraken, um modelo treinado no acervo) é melhor que o atual — com número, não
por impressão (diretriz 4.1).

Três medidas por página:

- **CER**: distância de edição entre os caracteres do candidato e os da
  referência, dividida pelo tamanho da referência. Espaço e quebra de linha
  não contam: o motor não é punido por quebrar a linha noutro lugar.
- **WER**: o mesmo, sobre palavras. Texto fora de ordem aumenta a distância,
  então o embaralhamento de linhas e colunas aparece no número.
- **WER com pontuação separada**: o WER depois de separar a pontuação das
  palavras. O datiloscrito escreve `Professores,quer`, o Kraken devolve
  `Professores, quer`, e o WER comum conta isso como duas palavras erradas.
  Espaço depois de vírgula é convenção tipográfica, não erro de leitura.
- **WER sem ordem**: compara as palavras como conjunto, ignorando a ordem.
  Para erro de leitura fica perto do WER; para texto só fora de ordem, perto de
  zero. A distância entre os dois é o tamanho do problema de ordem.

Fica separado de `avaliacao.py`, que mede recuperação: OCR ruim e busca ruim
têm correções diferentes. As referências e os candidatos ficam em
`data/avaliacao_ocr/`, fora do git — são texto integral do acervo.
"""

import json
import re
import time
import unicodedata
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from .erros import ErroConfiguracao
from .etapas import RelatorProgresso, sem_progresso
from .etapas.extracao import listar_pdfs, nome_seguro
from .modelos import LeituraDoMotor

# (pdf, número da página a partir de 1, idioma do Tesseract) → leitura.
MotorDeOcr = Callable[[Path, int, str], LeituraDoMotor]

# Palavras do idioma → as que o dicionário não conhece, ou `None` sem dicionário.
VerificadorDePalavras = Callable[[list[str], str], set[str] | None]

SUFIXO_DE_PAGINA = "_p"

PONTUACAO = re.compile(r"([,.;:!?\"“”«»()])")


@dataclass(frozen=True)
class PaginaDeTeste:
    """Uma página do acervo usada na avaliação."""

    identificador: str
    pdf: Path
    numero: int
    idioma: str


@dataclass
class ResultadoDaPagina:
    pagina: str
    motor: str
    cer: float
    wer: float
    wer_pontuacao_separada: float
    wer_sem_ordem: float
    caracteres_referencia: int
    caracteres_candidato: int
    tempo_s: float | None = None
    confianca_media: float | None = None
    fora_do_dicionario: float | None = None


def identificador(handle: str, arquivo: str, numero: int) -> str:
    """`7891/90109`, `FPF_OPF_01_0005.pdf`, 3 → `7891_90109_FPF_OPF_01_0005_p0003`.

    Leva o nome do arquivo porque um item pode ter mais de um PDF.
    """
    return f"{nome_seguro(handle)}_{Path(arquivo).stem}{SUFIXO_DE_PAGINA}{numero:04d}"


class MotorComReserva:
    """Usa o motor principal e só recorre à reserva quando a página sai quase vazia.

    O critério é o mesmo da extração, o mínimo de letras e dígitos, e não
    depende da referência: pode virar regra de produção sem ter sido ajustado
    ao gabarito.
    """

    def __init__(self, principal: MotorDeOcr, reserva: MotorDeOcr, minimo: int) -> None:
        self._principal, self._reserva, self._minimo = principal, reserva, minimo

    def __call__(self, pdf: Path, pagina: int, idioma: str) -> LeituraDoMotor:
        leitura = self._principal(pdf, pagina, idioma)
        if sum(1 for c in leitura.texto if c.isalnum()) >= self._minimo:
            return leitura
        return self._reserva(pdf, pagina, idioma)


# ── métricas ──────────────────────────────────────────────────────────────


def distancia_de_edicao(a: Sequence, b: Sequence) -> int:
    """Levenshtein: inserções, remoções e trocas para levar `a` a `b`.

    Prefixo e sufixo comuns saem antes: é a maior parte do texto quando dois
    motores quase concordam, e corta o custo quadrático onde ele mais pesa.
    """
    inicio = 0
    while inicio < len(a) and inicio < len(b) and a[inicio] == b[inicio]:
        inicio += 1
    fim_a, fim_b = len(a), len(b)
    while fim_a > inicio and fim_b > inicio and a[fim_a - 1] == b[fim_b - 1]:
        fim_a -= 1
        fim_b -= 1
    a, b = a[inicio:fim_a], b[inicio:fim_b]
    if len(a) < len(b):
        a, b = b, a
    if not b:
        return len(a)

    anterior = list(range(len(b) + 1))
    for i, item_a in enumerate(a, start=1):
        atual = [i]
        for j, item_b in enumerate(b, start=1):
            atual.append(min(anterior[j] + 1, atual[j - 1] + 1, anterior[j - 1] + (item_a != item_b)))
        anterior = atual
    return anterior[-1]


def normalizar(texto: str) -> str:
    """NFC, e todo espaço (inclusive quebra de linha e de página) vira um espaço só."""
    return " ".join(unicodedata.normalize("NFC", texto).split())


def _taxa(erros: int, tamanho: int) -> float:
    if tamanho:
        return erros / tamanho
    return 0.0 if not erros else 1.0


def cer(referencia: str, candidato: str) -> float:
    ref, cand = normalizar(referencia), normalizar(candidato)
    return _taxa(distancia_de_edicao(ref, cand), len(ref))


def wer(referencia: str, candidato: str) -> float:
    ref, cand = normalizar(referencia).split(), normalizar(candidato).split()
    return _taxa(distancia_de_edicao(ref, cand), len(ref))


def separar_pontuacao(texto: str) -> str:
    return PONTUACAO.sub(r" \1 ", texto)


def wer_pontuacao_separada(referencia: str, candidato: str) -> float:
    return wer(separar_pontuacao(referencia), separar_pontuacao(candidato))


def wer_sem_ordem(referencia: str, candidato: str) -> float:
    """Palavras como conjunto: a maior entre as que faltam e as que sobram.

    Uma palavra trocada falta e sobra ao mesmo tempo e conta 1, como no WER.
    Uma página só fora de ordem dá zero.
    """
    ref, cand = Counter(normalizar(referencia).split()), Counter(normalizar(candidato).split())
    faltam, sobram = sum((ref - cand).values()), sum((cand - ref).values())
    return _taxa(max(faltam, sobram), sum(ref.values()))


def fracao_fora_do_dicionario(texto: str, idioma: str, verificador: VerificadorDePalavras | None) -> float | None:
    """Das palavras só de letras, quantas o dicionário não conhece. `None` sem dicionário."""
    if verificador is None:
        return None
    palavras = [p.strip(".,;:!?()[]\"'“”«»—-") for p in normalizar(texto).split()]
    palavras = [p for p in palavras if p.isalpha()]
    if not palavras:
        return None
    desconhecidas = verificador(palavras, idioma)
    if desconhecidas is None:
        return None
    return sum(1 for p in palavras if p in desconhecidas) / len(palavras)


# ── páginas, referências e candidatos em disco ────────────────────────────


def resolver_paginas(
    identificadores: list[str], pasta_exportacao: Path, idioma_padrao: str
) -> tuple[list[PaginaDeTeste], list[str]]:
    """Identificador → PDF da exportação, número da página e idioma do catálogo."""
    pdfs, _ = listar_pdfs(pasta_exportacao)
    por_prefixo = {identificador(p.handle, p.arquivo, 0).rsplit(SUFIXO_DE_PAGINA, 1)[0]: p for p in pdfs}

    paginas, avisos = [], []
    for ident in identificadores:
        prefixo, _, numero = ident.rpartition(SUFIXO_DE_PAGINA)
        pdf = por_prefixo.get(prefixo)
        if pdf is None or not numero.isdigit():
            avisos.append(f"{ident}: não corresponde a nenhum PDF da exportação")
            continue
        paginas.append(PaginaDeTeste(ident, pdf.caminho, int(numero), pdf.idioma or idioma_padrao))
    return paginas, avisos


def referencias_existentes(base: Path) -> list[str]:
    pasta = base / "referencias"
    return sorted(p.stem for p in pasta.glob("*.txt")) if pasta.is_dir() else []


def motores_existentes(base: Path) -> list[str]:
    pasta = base / "candidatos"
    return sorted(p.name for p in pasta.iterdir() if p.is_dir()) if pasta.is_dir() else []


def gerar_candidatos(
    motores: dict[str, MotorDeOcr],
    paginas: list[PaginaDeTeste],
    base: Path,
    progresso: RelatorProgresso = sem_progresso,
) -> list[str]:
    """Roda cada motor em cada página e grava `candidatos/<motor>/<página>.txt` e `.json`.

    Página que falha vira aviso e não derruba as outras. Falta de programa ou de
    idioma interrompe: falharia igual em todas.
    """
    avisos: list[str] = []
    total, feito = len(motores) * len(paginas), 0
    for nome, motor in motores.items():
        pasta = base / "candidatos" / nome
        pasta.mkdir(parents=True, exist_ok=True)
        for pagina in paginas:
            inicio = time.monotonic()
            try:
                leitura = motor(pagina.pdf, pagina.numero, pagina.idioma)
            except ErroConfiguracao:
                raise
            except Exception as erro:
                avisos.append(f"{nome} / {pagina.identificador}: {erro}")
            else:
                (pasta / f"{pagina.identificador}.txt").write_text(leitura.texto, encoding="utf-8")
                registro = {
                    "tempo_s": round(time.monotonic() - inicio, 2),
                    "idioma": pagina.idioma,
                    "confianca_media": leitura.confianca_media,
                }
                (pasta / f"{pagina.identificador}.json").write_text(json.dumps(registro) + "\n", encoding="utf-8")
            feito += 1
            progresso(feito, total, f"{nome} · {pagina.identificador}")
    return avisos


def _ler_registro(caminho: Path) -> dict:
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def avaliar(
    base: Path,
    verificador: VerificadorDePalavras | None = None,
    progresso: RelatorProgresso = sem_progresso,
) -> tuple[list[ResultadoDaPagina], list[str]]:
    """Compara cada candidato em disco com a referência da mesma página."""
    referencias = referencias_existentes(base)
    motores = motores_existentes(base)
    if not referencias:
        raise ErroConfiguracao(
            f"Nenhuma transcrição de referência em {base / 'referencias'}.",
            "Grave uma por página, como <página>.txt, conferida contra a imagem.",
        )

    resultados: list[ResultadoDaPagina] = []
    avisos: list[str] = []
    total, feito = len(referencias) * len(motores), 0
    for pagina in referencias:
        referencia = (base / "referencias" / f"{pagina}.txt").read_text(encoding="utf-8")
        for motor in motores:
            feito += 1
            caminho = base / "candidatos" / motor / f"{pagina}.txt"
            if not caminho.is_file():
                avisos.append(f"{motor}: sem candidato para {pagina}")
                continue
            candidato = caminho.read_text(encoding="utf-8")
            registro = _ler_registro(caminho.with_suffix(".json"))
            resultados.append(
                ResultadoDaPagina(
                    pagina=pagina,
                    motor=motor,
                    cer=cer(referencia, candidato),
                    wer=wer(referencia, candidato),
                    wer_pontuacao_separada=wer_pontuacao_separada(referencia, candidato),
                    wer_sem_ordem=wer_sem_ordem(referencia, candidato),
                    caracteres_referencia=len(normalizar(referencia)),
                    caracteres_candidato=len(normalizar(candidato)),
                    tempo_s=registro.get("tempo_s"),
                    confianca_media=registro.get("confianca_media"),
                    fora_do_dicionario=fracao_fora_do_dicionario(candidato, registro.get("idioma", ""), verificador),
                )
            )
            progresso(feito, total, f"{motor} · {pagina}")
    return resultados, avisos


def media_por_motor(resultados: list[ResultadoDaPagina]) -> dict[str, dict[str, float]]:
    """Média simples por motor: cada página pesa igual, curta ou longa."""
    por_motor: dict[str, list[ResultadoDaPagina]] = {}
    for resultado in resultados:
        por_motor.setdefault(resultado.motor, []).append(resultado)

    def media(valores: list[float | None]) -> float | None:
        presentes = [v for v in valores if v is not None]
        return sum(presentes) / len(presentes) if presentes else None

    return {
        motor: {
            "paginas": len(lista),
            "cer": media([r.cer for r in lista]),
            "wer": media([r.wer for r in lista]),
            "wer_pontuacao_separada": media([r.wer_pontuacao_separada for r in lista]),
            "wer_sem_ordem": media([r.wer_sem_ordem for r in lista]),
            "tempo_s": media([r.tempo_s for r in lista]),
            "fora_do_dicionario": media([r.fora_do_dicionario for r in lista]),
        }
        for motor, lista in sorted(por_motor.items())
    }
