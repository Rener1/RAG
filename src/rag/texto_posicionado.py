"""
Texto posicionado: a página como regiões, linhas e palavras, com coordenadas e confiança.

É o artefato mestre do texto do acervo (roadmap §4, item 7, fase 2). O `.txt`
que o recorte consome é **derivado** dele: segue a ordem de leitura e pula as
regiões que não são conteúdo (carimbo, ruído dos furos). Por isso desligar uma
regra de região não exige refazer o OCR — basta derivar de novo.

O formato em disco é PAGE XML 2019, o que o Kraken escreve e o eScriptorium
importa e exporta. Só um subconjunto é lido e escrito: regiões de texto com
tipo, linhas com linha de base, palavras com confiança e a ordem de leitura.
Os glifos (um elemento por caractere) ficam de fora: multiplicam o arquivo por
dez e a confiança por palavra basta para a nota de qualidade.

Fica na raiz do pacote, e não em `etapas/`, porque a extração e a revisão o
usam, e uma etapa não importa outra.

O tipo da região vai no atributo `custom` (`structure {type:carimbo;}`), a
convenção de tipologia livre do PAGE, porque o atributo `type` do esquema só
aceita uma lista fixa em inglês. O Kraken 7.1 escreve `type {type:text;}`, e a
leitura aceita as duas formas.
"""

import re
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from difflib import SequenceMatcher

from .config import ConfigRegioes

NS_PAGE = "http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15"
_P = f"{{{NS_PAGE}}}"
NS_XSI = "http://www.w3.org/2001/XMLSchema-instance"
# O eScriptorium escolhe o esquema pelo `xsi:schemaLocation` e recusa o arquivo
# sem ele ("Cannot Find Schema location"), mesmo com o namespace certo.
LOCAL_DO_ESQUEMA = f"{NS_PAGE} {NS_PAGE}/pagecontent.xsd"

TIPO_TEXTO = "texto"
TIPO_CARIMBO = "carimbo"
TIPO_RUIDO = "ruido"
TIPO_NUMERO_DE_PAGINA = "numero_de_pagina"

# Os nomes que o Kraken e o eScriptorium dão à região comum. O resto é mantido
# como veio: um tipo criado na revisão (legenda, título) chega intacto.
_SINONIMOS_DE_TEXTO = {"", "text", "default", "texto", "paragraph"}

# CATMuS e outras transcrições marcam o hífen de fim de linha com `¬`. No PAGE
# ele fica como veio, porque diz "esta palavra continua na linha de baixo" —
# é o que a normalização (roadmap item 9) vai usar para juntar a palavra.
HIFEN_DE_FIM_DE_LINHA = "¬"

Ponto = tuple[int, int]
Caixa = tuple[int, int, int, int]  # x0, y0, x1, y1


@dataclass(frozen=True)
class Palavra:
    texto: str
    contorno: tuple[Ponto, ...] = ()
    confianca: float | None = None


@dataclass(frozen=True)
class Linha:
    id: str
    texto: str
    contorno: tuple[Ponto, ...] = ()
    linha_de_base: tuple[Ponto, ...] = ()
    palavras: tuple[Palavra, ...] = ()
    confianca: float | None = None

    @property
    def caixa(self) -> Caixa:
        return caixa_de(self.contorno or self.linha_de_base)


@dataclass(frozen=True)
class Regiao:
    id: str
    tipo: str
    contorno: tuple[Ponto, ...] = ()
    linhas: tuple[Linha, ...] = ()


@dataclass(frozen=True)
class PaginaPosicionada:
    """As regiões estão na ordem de leitura."""

    largura: int
    altura: int
    imagem: str = ""
    regioes: tuple[Regiao, ...] = ()

    @property
    def tem_posicao(self) -> bool:
        """Falso para o texto de um motor que não dá coordenadas (OCRmyPDF)."""
        return self.largura > 0 and self.altura > 0

    def confianca_media(self, ignorar: frozenset[str] = frozenset()) -> float | None:
        """Média da confiança das palavras, fora as regiões ignoradas. `None` sem nenhuma."""
        valores = [
            palavra.confianca
            for regiao in self.regioes
            if regiao.tipo not in ignorar
            for linha in regiao.linhas
            for palavra in linha.palavras
            if palavra.confianca is not None
        ]
        return sum(valores) / len(valores) if valores else None

    def contagem_por_tipo(self) -> dict[str, int]:
        """Linhas por tipo de região — o que vai ao registro da extração."""
        contagem: dict[str, int] = {}
        for regiao in self.regioes:
            contagem[regiao.tipo] = contagem.get(regiao.tipo, 0) + len(regiao.linhas)
        return contagem


def caixa_de(pontos: tuple[Ponto, ...]) -> Caixa:
    if not pontos:
        return (0, 0, 0, 0)
    xs = [x for x, _ in pontos]
    ys = [y for _, y in pontos]
    return (min(xs), min(ys), max(xs), max(ys))


def pagina_sem_posicao(texto: str) -> PaginaPosicionada:
    """Embrulha o texto de um motor sem coordenadas: um bloco por região, uma linha por linha.

    `texto_da_pagina` devolve o mesmo texto, com as linhas em branco
    repetidas reduzidas a uma. Sem coordenadas não há PAGE XML a gravar nem
    regra de região a aplicar — `tem_posicao` diz isso a quem usa.
    """
    blocos = [b for b in re.split(r"\n\s*\n", texto) if b.strip()]
    regioes = tuple(
        Regiao(f"r{i}", TIPO_TEXTO, linhas=tuple(Linha(f"r{i}_l{j}", t) for j, t in enumerate(b.splitlines())))
        for i, b in enumerate(blocos)
    )
    return PaginaPosicionada(largura=0, altura=0, regioes=regioes)


# ── leitura e escrita do PAGE ─────────────────────────────────────────────


def _pontos(elemento: ET.Element | None, marca: str = "Coords") -> tuple[Ponto, ...]:
    alvo = elemento.find(_P + marca) if elemento is not None else None
    if alvo is None or not alvo.get("points"):
        return ()
    pontos = []
    for par in alvo.get("points", "").split():
        x, _, y = par.partition(",")
        pontos.append((int(float(x)), int(float(y))))
    return tuple(pontos)


def _texto_e_confianca(elemento: ET.Element) -> tuple[str, float | None]:
    equivalente = elemento.find(_P + "TextEquiv")
    if equivalente is None:
        return "", None
    unicode = equivalente.find(_P + "Unicode")
    confianca = equivalente.get("conf")
    return (unicode.text or "") if unicode is not None else "", float(confianca) if confianca else None


_TIPO_NO_CUSTOM = re.compile(r"(?:structure|type)\s*\{[^}]*?\btype\s*:\s*([^;}]+)")


def tipo_da_regiao(elemento: ET.Element) -> str:
    """O tipo pelo `custom` (Kraken, eScriptorium) ou pelo `type` do esquema."""
    encontrado = _TIPO_NO_CUSTOM.search(elemento.get("custom", ""))
    bruto = encontrado.group(1).strip() if encontrado else elemento.get("type", "")
    return TIPO_TEXTO if bruto.lower() in _SINONIMOS_DE_TEXTO else bruto


def _ordem_de_leitura(pagina: ET.Element) -> list[str]:
    grupo = pagina.find(f"{_P}ReadingOrder/{_P}OrderedGroup")
    if grupo is None:
        return []
    referencias = grupo.findall(_P + "RegionRefIndexed")
    return [r.get("regionRef", "") for r in sorted(referencias, key=lambda r: int(r.get("index", "0")))]


def ler_page_xml(conteudo: str | bytes) -> PaginaPosicionada:
    """Lê um PAGE XML 2019. Sem `ReadingOrder`, a ordem é a do documento.

    Região que a ordem de leitura não cita vai para o fim, na ordem do
    documento — some do texto derivado só se o tipo dela mandar.
    """
    raiz = ET.fromstring(conteudo)
    pagina = raiz.find(_P + "Page")
    if pagina is None:
        raise ValueError("PAGE XML sem o elemento Page.")

    regioes = []
    for elemento in pagina.iter(_P + "TextRegion"):
        linhas = []
        for linha in elemento.findall(_P + "TextLine"):
            # O Kraken grava cada espaço como um `Word` de texto " ". O eScriptorium
            # junta as palavras com espaço para formar a linha, e importaria espaços
            # triplos; sem elas, a junção reproduz o texto da linha (conferido nas
            # 238 linhas do 7891/1133).
            palavras = tuple(
                Palavra(texto, _pontos(palavra), confianca)
                for palavra in linha.findall(_P + "Word")
                for texto, confianca in [_texto_e_confianca(palavra)]
                if texto.strip()
            )
            texto, confianca = _texto_e_confianca(linha)
            linhas.append(
                Linha(
                    id=linha.get("id", ""),
                    texto=texto,
                    contorno=_pontos(linha),
                    linha_de_base=_pontos(linha, "Baseline"),
                    palavras=palavras,
                    confianca=confianca,
                )
            )
        regioes.append(Regiao(elemento.get("id", ""), tipo_da_regiao(elemento), _pontos(elemento), tuple(linhas)))

    ordem = {id_: posicao for posicao, id_ in enumerate(_ordem_de_leitura(pagina))}
    regioes.sort(key=lambda r: ordem.get(r.id, len(ordem)))  # sort é estável: o resto mantém a ordem

    return PaginaPosicionada(
        largura=int(pagina.get("imageWidth", "0")),
        altura=int(pagina.get("imageHeight", "0")),
        imagem=pagina.get("imageFilename", ""),
        regioes=tuple(regioes),
    )


def _formatar_pontos(pontos: tuple[Ponto, ...]) -> str:
    return " ".join(f"{x},{y}" for x, y in pontos)


def _sub(pai: ET.Element, marca: str, **atributos: str) -> ET.Element:
    return ET.SubElement(pai, _P + marca, {k: v for k, v in atributos.items() if v})


def _equivalente(pai: ET.Element, texto: str, confianca: float | None) -> None:
    equivalente = _sub(pai, "TextEquiv", conf="" if confianca is None else f"{confianca:.4g}")
    _sub(equivalente, "Unicode").text = texto


def _contorno(pai: ET.Element, pontos: tuple[Ponto, ...], marca: str = "Coords") -> None:
    # Coords é obrigatório no esquema; sem pontos, um ponto na origem o satisfaz.
    _sub(pai, marca, points=_formatar_pontos(pontos) or "0,0")


def escrever_page_xml(pagina: PaginaPosicionada, criador: str = "rag") -> str:
    """Serializa em PAGE XML 2019, com a ordem de leitura explícita."""
    ET.register_namespace("", NS_PAGE)
    ET.register_namespace("xsi", NS_XSI)
    agora = datetime.now(UTC).isoformat(timespec="seconds")

    raiz = ET.Element(_P + "PcGts", {f"{{{NS_XSI}}}schemaLocation": LOCAL_DO_ESQUEMA})
    metadados = _sub(raiz, "Metadata")
    _sub(metadados, "Creator").text = criador
    _sub(metadados, "Created").text = agora
    _sub(metadados, "LastChange").text = agora

    elemento_pagina = _sub(
        raiz,
        "Page",
        imageFilename=pagina.imagem or "pagina.png",
        imageWidth=str(pagina.largura),
        imageHeight=str(pagina.altura),
    )
    if pagina.regioes:
        grupo = _sub(_sub(elemento_pagina, "ReadingOrder"), "OrderedGroup", id="ordem_de_leitura")
        for indice, regiao in enumerate(pagina.regioes):
            _sub(grupo, "RegionRefIndexed", index=str(indice), regionRef=regiao.id)

    for regiao in pagina.regioes:
        elemento = _sub(elemento_pagina, "TextRegion", id=regiao.id, custom=f"structure {{type:{regiao.tipo};}}")
        # Região sem contorno (criada por regra) ganha o retângulo das linhas:
        # é o que o eScriptorium desenha para a revisora.
        _contorno(elemento, regiao.contorno or (_contorno_retangular(regiao.linhas) if regiao.linhas else ()))
        for linha in regiao.linhas:
            elemento_linha = _sub(elemento, "TextLine", id=linha.id)
            _contorno(elemento_linha, linha.contorno)
            if linha.linha_de_base:
                _contorno(elemento_linha, linha.linha_de_base, "Baseline")
            for indice, palavra in enumerate(linha.palavras):
                elemento_palavra = _sub(elemento_linha, "Word", id=f"{linha.id}_p{indice}")
                _contorno(elemento_palavra, palavra.contorno)
                _equivalente(elemento_palavra, palavra.texto, palavra.confianca)
            _equivalente(elemento_linha, linha.texto, linha.confianca)

    ET.indent(raiz)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(raiz, encoding="unicode") + "\n"


# ── texto derivado ────────────────────────────────────────────────────────


def tipos_ignorados(config: ConfigRegioes) -> frozenset[str]:
    return frozenset(t.strip() for t in config.tipos_ignorados.split("|") if t.strip())


def texto_da_pagina(pagina: PaginaPosicionada, ignorar: frozenset[str] = frozenset({TIPO_CARIMBO, TIPO_RUIDO})) -> str:
    """O texto na ordem de leitura: uma linha por linha, uma linha em branco entre regiões.

    A linha em branco é o que o recorte entende como fim de parágrafo, e uma
    região do Kraken costuma ser um bloco contínuo do papel.
    """
    blocos = []
    for regiao in pagina.regioes:
        if regiao.tipo in ignorar:
            continue
        linhas = [linha.texto.replace(HIFEN_DE_FIM_DE_LINHA, "-") for linha in regiao.linhas if linha.texto.strip()]
        if linhas:
            blocos.append("\n".join(linhas))
    return "\n\n".join(blocos)


# ── regras de região ──────────────────────────────────────────────────────


def _caracteres_uteis(texto: str) -> int:
    return sum(1 for c in texto if c.isalnum())


def _comparavel(texto: str) -> str:
    """Caixa e acento fora, pontuação vira espaço: o OCR erra mais nisso que nas letras."""
    sem_acento = "".join(c for c in unicodedata.normalize("NFKD", texto.casefold()) if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^\w]+", " ", sem_acento).split())


def semelhanca(a: str, b: str) -> float:
    return SequenceMatcher(None, _comparavel(a), _comparavel(b)).ratio()


def linhas_de_carimbo(config: ConfigRegioes) -> list[str]:
    return [linha.strip() for linha in config.carimbos.split("|") if linha.strip()]


def _parece_carimbo(linha: Linha, carimbos: list[str], limiar: float) -> bool:
    return bool(linha.texto.strip()) and max((semelhanca(linha.texto, c) for c in carimbos), default=0.0) >= limiar


def _contorno_retangular(linhas: tuple[Linha, ...]) -> tuple[Ponto, ...]:
    x0, y0, x1, y1 = caixa_de(tuple(p for linha in linhas for p in (linha.contorno or linha.linha_de_base)))
    return ((x0, y0), (x1, y0), (x1, y1), (x0, y1))


def separar_carimbo(pagina: PaginaPosicionada, config: ConfigRegioes) -> PaginaPosicionada:
    """Tira as linhas do carimbo da região em que o segmentador as pôs.

    Uma linha é do carimbo quando está na zona do rodapé **e** se parece com
    uma linha conhecida de carimbo. Os dois critérios juntos: só o texto
    pegaria uma carta que cita o Instituto, só a posição pegaria a última linha
    do texto. E é preciso um mínimo de linhas assim na mesma região — o
    carimbo tem várias, uma coincidência tem uma.

    As linhas do carimbo viram uma região própria logo depois da de origem,
    com as coordenadas intactas: a revisora a vê no eScriptorium e desfaz se
    a regra errar.
    """
    carimbos = linhas_de_carimbo(config)
    if not config.marcar_carimbo or not carimbos or not pagina.tem_posicao:
        return pagina

    topo_da_zona = pagina.altura * (1 - config.zona_do_carimbo)
    regioes: list[Regiao] = []
    for regiao in pagina.regioes:
        if regiao.tipo != TIPO_TEXTO:
            regioes.append(regiao)
            continue
        do_carimbo = tuple(
            linha
            for linha in regiao.linhas
            if linha.caixa[1] >= topo_da_zona and _parece_carimbo(linha, carimbos, config.semelhanca_do_carimbo)
        )
        if len(do_carimbo) < config.minimo_de_linhas_do_carimbo:
            regioes.append(regiao)
            continue
        regioes += _mover_linhas(regiao, do_carimbo, TIPO_CARIMBO)
    return replace(pagina, regioes=tuple(regioes))


def _mover_linhas(regiao: Regiao, linhas: tuple[Linha, ...], tipo: str) -> list[Regiao]:
    """A região sem as linhas, seguida de uma região nova do `tipo` só com elas."""
    restantes = tuple(linha for linha in regiao.linhas if linha not in linhas)
    nova = Regiao(f"{regiao.id}_{tipo}", tipo, _contorno_retangular(linhas), linhas)
    return [replace(regiao, linhas=restantes), nova] if restantes else [nova]


_NUMERO_DE_PAGINA = re.compile(r"^\W*\d{1,4}\W*$")


def _fragmento(texto: str, config: ConfigRegioes) -> bool:
    # Dígito solto conta: os furos viram "3", "2", "9" com frequência, e o
    # número de página fica no alto, longe da faixa da margem.
    return _caracteres_uteis(texto) <= config.maximo_de_caracteres_do_ruido


def marcar_ruido(pagina: PaginaPosicionada, config: ConfigRegioes) -> PaginaPosicionada:
    """Marca o ruído dos furos de encadernação, e a região de número de página.

    Os furos saem como dezenas de "linhas" de uma ou duas letras na margem
    (7891/1133). O segmentador ora os separa numa região estreita, ora os
    deixa dentro da região do corpo, e por isso há duas regras:

    - região em que **toda** linha é fragmento (até `maximo_de_caracteres_do_ruido`
      letras e números), com ao menos três linhas, vira ruído inteira;
    - dentro das outras, a linha que é fragmento e cabe **inteira** na faixa da
      margem (`margem_do_ruido`, de cada lado) vai para uma região de ruído.
      Fragmento fora da margem fica: no 7891/1133 p. 1 é anotação a caneta (P7),
      que é decisão de revisão, não de regra.

    O número de página é uma linha só de dígitos e pontuação (`-2-`), marcado
    à parte para não ir junto: é a página impressa, que pode servir à citação.
    """
    # Sem coordenadas, "região" é só parágrafo, e uma lista numerada (`1.`,
    # `2.`, `3.`) passaria por furo de encadernação.
    if not config.marcar_ruido or not pagina.tem_posicao:
        return pagina

    esquerda = pagina.largura * config.margem_do_ruido
    direita = pagina.largura * (1 - config.margem_do_ruido)
    regioes: list[Regiao] = []
    for regiao in pagina.regioes:
        textos = [linha.texto for linha in regiao.linhas if linha.texto.strip()]
        if regiao.tipo != TIPO_TEXTO:
            regioes.append(regiao)
        elif len(textos) == 1 and _NUMERO_DE_PAGINA.match(textos[0]):
            regioes.append(replace(regiao, tipo=TIPO_NUMERO_DE_PAGINA))
        elif len(textos) >= 3 and all(_caracteres_uteis(t) <= config.maximo_de_caracteres_do_ruido for t in textos):
            regioes.append(replace(regiao, tipo=TIPO_RUIDO))
        else:
            na_margem = tuple(
                linha
                for linha in regiao.linhas
                if _fragmento(linha.texto, config) and (linha.caixa[2] <= esquerda or linha.caixa[0] >= direita)
            )
            regioes += _mover_linhas(regiao, na_margem, TIPO_RUIDO) if na_margem else [regiao]
    return replace(pagina, regioes=tuple(regioes))


def classificar_regioes(pagina: PaginaPosicionada, config: ConfigRegioes) -> PaginaPosicionada:
    """Aplica as regras de região, cada uma desligável na configuração.

    É o primeiro de três jeitos de marcar o tipo da região, e o mais fraco: a
    revisora corrige no eScriptorium, e um modelo de segmentação treinado no
    acervo substitui a regra ([registro do OCR](docs/acervo/revisao-do-ocr.md) §6).
    """
    return separar_carimbo(marcar_ruido(pagina, config), config)
