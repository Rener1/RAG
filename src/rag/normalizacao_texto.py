"""
Normalização do texto depois do OCR (roadmap §4, item 9).

Regras puras sobre a página vista como blocos de linhas: um bloco é uma região
do texto posicionado, ou um parágrafo do texto digital. Cada regra pode ser
desligada (`ConfigNormalizacao`) e é contada, para a medição e a auditoria.

O dicionário só **julga junção**, nunca troca palavra: corrigir sozinho troca
uma palavra por outra que existe, o erro mais caro do registro de revisão do
OCR. Sem dicionário do idioma, as regras que dependem dele não se aplicam, e a
do `¬` continua — ela não precisa de dicionário, o Kraken já disse que a
palavra continua.

Fica na raiz do pacote porque a etapa de normalização e a avaliação do OCR a
usam, e uma etapa não importa outra.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from .config import ConfigNormalizacao
from .texto_posicionado import HIFEN_DE_FIM_DE_LINHA, PaginaPosicionada

# Palavras → as que o dicionário não conhece, ou `None` sem dicionário. É o
# `VerificadorDePalavras` com o idioma já fixado.
Desconhecidas = Callable[[list[str]], set[str] | None]

Bloco = list[str]

REGRA_HIFEN_MARCADO = "hifen_marcado"
REGRA_HIFEN_COMUM = "hifen_comum"
REGRA_HIFEN_MANTIDO = "hifen_mantido"
REGRA_SEM_HIFEN = "sem_hifen"
REGRA_PONTUACAO = "pontuacao"

# A palavra no fim da linha (com o hífen, se houver) e no começo da seguinte.
_FIM = re.compile(r"(\w+)([-¬]?)$")
_COMECO = re.compile(r"^(\w+)")
_SO_LETRAS = re.compile(r"^[^\W\d_]+$")

# Pontuação colada à palavra seguinte. Vírgula e afins antes de qualquer letra;
# ponto, exclamação e interrogação só entre minúscula e maiúscula que não
# abre abreviação: poupa sigla e código (`U.S.A.`, `FPF.OPF`) e `Ph.D.`.
# Duas letras antes poupam a sigla na vírgula também.
_VIRGULA_COLADA = re.compile(r"(?<=[^\W\d_]{2})([,;:])(?=[^\W\d_])")
_PONTO_COLADO = re.compile(r"(?<=[a-zà-ÿ]{2})([.!?])(?=[A-ZÀ-Ý](?![.]))")
# Token que é endereço não se mexe: e-mail, URL, domínio.
_ENDERECO = re.compile(r"@|://|^www\.|\.(org|com|br|net|edu|gov|fr|es)\b", re.IGNORECASE)


@dataclass
class PaginaNormalizada:
    texto: str
    contagens: dict[str, int] = field(default_factory=dict)
    exemplos: dict[str, list[str]] = field(default_factory=dict)

    def contar(self, regra: str, exemplo: str, limite: int) -> None:
        self.contagens[regra] = self.contagens.get(regra, 0) + 1
        lista = self.exemplos.setdefault(regra, [])
        if len(lista) < limite:
            lista.append(exemplo)


# ── a página em blocos ────────────────────────────────────────────────────


def blocos_da_pagina_posicionada(pagina: PaginaPosicionada, ignorar: frozenset[str]) -> list[Bloco]:
    """Um bloco por região, na ordem de leitura, sem os tipos ignorados. Mantém o `¬`."""
    blocos = []
    for regiao in pagina.regioes:
        if regiao.tipo in ignorar:
            continue
        linhas = [linha.texto.strip() for linha in regiao.linhas if linha.texto.strip()]
        if linhas:
            blocos.append(linhas)
    return blocos


def blocos_do_texto(texto: str) -> list[Bloco]:
    """Blocos separados por linha em branco — a forma que `texto_da_pagina` e o texto digital têm."""
    blocos = []
    for pedaco in re.split(r"\n\s*\n", texto):
        linhas = [linha.strip() for linha in pedaco.splitlines() if linha.strip()]
        if linhas:
            blocos.append(linhas)
    return blocos


# ── junção das palavras partidas ──────────────────────────────────────────


@dataclass(frozen=True)
class _Corte:
    """Onde uma palavra pode ter sido partida: fim da linha `i` do bloco `b` e começo da seguinte."""

    bloco: int
    linha: int
    antes: str
    hifen: str
    depois: str


def _cortes(blocos: list[Bloco]) -> list[_Corte]:
    cortes = []
    for b, bloco in enumerate(blocos):
        for i in range(len(bloco) - 1):
            fim, comeco = _FIM.search(bloco[i]), _COMECO.match(bloco[i + 1])
            if not fim or not comeco:
                continue
            antes, hifen, depois = fim.group(1), fim.group(2), comeco.group(1)
            # Só palavra de letras, e a continuação começa minúscula: maiúscula
            # no começo da linha é começo de frase ou nome, não meio de palavra.
            if _SO_LETRAS.match(antes) and _SO_LETRAS.match(depois) and depois[0].islower():
                cortes.append(_Corte(b, i, antes, hifen, depois))
    return cortes


def _decidir(corte: _Corte, desconhecidas: set[str] | None, config: ConfigNormalizacao) -> tuple[str, str] | None:
    """Como juntar o corte: (regra, junção) — junção "" sem hífen, "-" com. `None` deixa como está."""
    if corte.hifen == HIFEN_DE_FIM_DE_LINHA:
        if not config.juntar_hifen_marcado:
            return None
        # O CATMuS marca com `¬` também o hífen que fica: ênclise e composta
        # (`tornando¬` / `se`). Com dicionário, as duas metades existindo e a
        # junta não, o hífen fica. Sem dicionário, o `¬` basta para juntar.
        if desconhecidas is not None:
            junta = corte.antes + corte.depois
            if junta in desconhecidas and corte.antes not in desconhecidas and corte.depois not in desconhecidas:
                return REGRA_HIFEN_MANTIDO, "-"
        return REGRA_HIFEN_MARCADO, ""
    if desconhecidas is None:
        # Sem dicionário, hífen no fim da linha fica hífen, mas a palavra se
        # reúne: `sócio-` / `político` é `sócio-político`, nunca `sócio- político`.
        return (REGRA_HIFEN_MANTIDO, "-") if corte.hifen and config.juntar_hifen_comum else None
    junta = corte.antes + corte.depois
    junta_existe = junta not in desconhecidas
    metade_nao_existe = corte.antes in desconhecidas or corte.depois in desconhecidas
    if corte.hifen:
        # Hífen no fim da linha é quase sempre corte de sílaba, mesmo quando as
        # metades existem (`senti-` / `do`). Composta grudada não está no
        # dicionário (`sóciopolítico`, `pósgraduação`), e é isso que a poupa.
        if not config.juntar_hifen_comum:
            return None
        return (REGRA_HIFEN_COMUM, "") if junta_existe else (REGRA_HIFEN_MANTIDO, "-")
    # Pedaço curto engana: `vel` / `e` daria `vele`, `o` / `va` daria `ova`.
    curta = len(junta) < config.minimo_da_junta_sem_hifen
    if config.juntar_sem_hifen and junta_existe and metade_nao_existe and not curta:
        return REGRA_SEM_HIFEN, ""
    return None


def _juntar_palavras(
    blocos: list[Bloco],
    desconhecidas_de: Desconhecidas | None,
    config: ConfigNormalizacao,
    resultado: PaginaNormalizada,
) -> list[Bloco]:
    cortes = _cortes(blocos)
    desconhecidas: set[str] | None = None
    precisam_de_dicionario = cortes
    if precisam_de_dicionario and desconhecidas_de is not None:
        # Uma consulta só por página, com todas as candidatas.
        candidatas = sorted({p for c in precisam_de_dicionario for p in (c.antes, c.depois, c.antes + c.depois)})
        desconhecidas = desconhecidas_de(candidatas)

    blocos = [list(bloco) for bloco in blocos]
    # De trás para a frente: juntar uma linha com a seguinte não desloca as anteriores.
    for corte in reversed(cortes):
        decisao = _decidir(corte, desconhecidas, config)
        if decisao is None:
            continue
        regra, juncao = decisao
        bloco = blocos[corte.bloco]
        atual, seguinte = bloco[corte.linha], bloco[corte.linha + 1]
        cabeca = atual[: len(atual) - len(corte.hifen)]
        resto = seguinte[len(corte.depois) :]
        bloco[corte.linha] = cabeca + juncao + corte.depois + resto
        del bloco[corte.linha + 1]
        resultado.contar(regra, f"{corte.antes}{corte.hifen} / {corte.depois}", config.exemplos_por_regra)
    return blocos


# ── espaços e pontuação ───────────────────────────────────────────────────


def _separar_pontuacao(texto: str, config: ConfigNormalizacao, resultado: PaginaNormalizada) -> str:
    tokens = texto.split(" ")
    for i, token in enumerate(tokens):
        if not token or _ENDERECO.search(token):
            continue
        novo = _PONTO_COLADO.sub(r"\1 ", _VIRGULA_COLADA.sub(r"\1 ", token))
        if novo != token:
            resultado.contar(REGRA_PONTUACAO, token, config.exemplos_por_regra)
            tokens[i] = novo
    return " ".join(tokens)


def normalizar_blocos(
    blocos: list[Bloco], config: ConfigNormalizacao, desconhecidas_de: Desconhecidas | None = None
) -> PaginaNormalizada:
    """A página normalizada: palavras partidas juntas, um parágrafo por bloco, espaços em ordem."""
    resultado = PaginaNormalizada(texto="")
    blocos = _juntar_palavras(blocos, desconhecidas_de, config, resultado)
    paragrafos = []
    for bloco in blocos:
        # O `¬` que sobrou (fim de região, ou regra desligada) vira hífen comum.
        linhas = [linha.replace(HIFEN_DE_FIM_DE_LINHA, "-") for linha in bloco]
        separador = " " if config.juntar_linhas else "\n"
        texto = separador.join(linhas)
        texto = re.sub(r"[ \t]+", " ", texto).strip()
        if config.espaco_apos_pontuacao:
            texto = _separar_pontuacao(texto, config, resultado)
        if texto:
            paragrafos.append(texto)
    resultado.texto = "\n\n".join(paragrafos)
    return resultado
