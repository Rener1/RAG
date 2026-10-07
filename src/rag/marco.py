"""
O marco pedagógico — leitura e validação.

O marco é a "constituição freiriana" do sistema: um documento em linguagem
natural, escrito pelo comitê pedagógico e não por programadores, que define
como o sistema se comporta, o que recusa fazer, que perguntas devolve antes de
responder e em que formato entrega. Os documentos de origem são explícitos em
três exigências que um prompt no código não atende
(`docs/plano/fase-2-prototipo.md` §4.6): ele é versionado com diff legível, editável
sem deploy por quem não programa, e toda alteração dispara o harness.

Daí o formato: Markdown com frontmatter. O comitê escreve prosa, e prosa em
YAML ou JSON significa aspas, indentação e escape que quebram em silêncio e
produzem diff ilegível. Em `.md` o diff é linha de prosa, e a única sintaxe a
respeitar é `## nome-da-seção`.

Mora na raiz do pacote, e não em `etapas/`, porque `etapas/geracao.py` depende
do protocolo `MarcoPedagogico` — não deste módulo.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from .erros import ErroMarcoInvalido

# Sem estes três campos não dá para citar quem escreveu o quê, e o comitê tem
# veto sobre mudanças de comportamento — veto sem versão não é exercível.
CAMPOS_OBRIGATORIOS = ("nome", "versao", "autoria")

# O mínimo para o marco montar um prompt de resposta.
SECOES_OBRIGATORIAS = ("papel", "instrucoes", "formato_de_saida")

# Seções lidas por outras camadas (mediação e sessão), que não entram no prompt
# da resposta. Uma seção fora desta lista e das obrigatórias é acrescentada ao
# prompt de resposta na ordem em que aparece no arquivo.
SECOES_DE_ORQUESTRACAO = ("decomposicao", "triagem", "problematizacao")

# Ordem preferida das seções conhecidas dentro do prompt de resposta.
ORDEM_NA_RESPOSTA = ("papel", "instrucoes", "recusas", "formato_de_saida")

# Arquivos de `marcos/` que não são marcos.
NOMES_IGNORADOS = {"LEIA-ME", "README"}

PADRAO_CABECALHO = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


def normalizar_nome_de_secao(bruto: str) -> str:
    """'Formato de Saída' → 'formato_de_saida'.

    Existe para que acento, maiúscula e espaço no cabeçalho não virem erro. É o
    tipo de tropeço que quem escreve prosa comete o tempo todo, e que não
    deveria custar um chamado ao programador.
    """
    sem_acento = "".join(c for c in unicodedata.normalize("NFKD", bruto) if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "_", sem_acento.strip().lower()).strip("_")


@dataclass(frozen=True, slots=True)
class Marco:
    """Um marco carregado. Cumpre o protocolo `MarcoPedagogico`."""

    identificador: str  # nome do arquivo sem .md
    nome: str
    versao: str
    autoria: str
    metadados: dict[str, str] = field(default_factory=dict)
    secoes: dict[str, str] = field(default_factory=dict)
    titulos: dict[str, str] = field(default_factory=dict)  # normalizado → como escrito
    caminho: Path | None = None

    def secao(self, nome: str, padrao: str = "") -> str:
        return self.secoes.get(normalizar_nome_de_secao(nome), padrao)

    def metadado(self, nome: str, padrao: str = "") -> str:
        return self.metadados.get(normalizar_nome_de_secao(nome), padrao)

    def diz_sim(self, nome: str, padrao: bool) -> bool:
        """Lê um metadado escrito como sim/não. Valor ausente devolve o padrão."""
        valor = self.metadado(nome).strip().casefold()
        if not valor:
            return padrao
        return valor in {"sim", "s", "true", "1", "yes"}

    def secoes_de_resposta(self) -> list[tuple[str, str]]:
        """As seções que orientam a resposta, na ordem em que entram no prompt.

        As conhecidas vêm primeiro, na ordem de `ORDEM_NA_RESPOSTA`; as que o
        comitê acrescentou vêm depois, na ordem do arquivo. As de orquestração
        ficam de fora — são lidas pela mediação e pela sessão.
        """
        extras = [nome for nome in self.secoes if nome not in ORDEM_NA_RESPOSTA and nome not in SECOES_DE_ORQUESTRACAO]
        ordem = [nome for nome in ORDEM_NA_RESPOSTA if nome in self.secoes] + extras
        return [(self.titulos.get(nome, nome), self.secoes[nome]) for nome in ordem]

    def resumo(self) -> str:
        return f"{self.identificador} v{self.versao} — {self.autoria} · {len(self.secoes)} seções"


# ── análise ───────────────────────────────────────────────────────────────


def separar_frontmatter(conteudo: str) -> tuple[dict[str, str], str]:
    """Separa o bloco entre `---` do corpo. Erra alto se o bloco não existir."""
    linhas = conteudo.lstrip("\ufeff").lstrip().splitlines()

    if not linhas or linhas[0].strip() != "---":
        raise ErroMarcoInvalido(
            "O marco precisa começar com uma linha '---'.",
            sugestao="Abra o arquivo com o bloco de identificação:\n"
            "      ---\n      nome: ...\n      versao: 1\n      autoria: ...\n      ---",
        )

    try:
        fim = next(i for i, linha in enumerate(linhas[1:], start=1) if linha.strip() == "---")
    except StopIteration:
        raise ErroMarcoInvalido(
            "O bloco de identificação foi aberto com '---' e nunca fechado.",
            sugestao="Feche o bloco com outra linha contendo só '---'.",
        ) from None

    metadados: dict[str, str] = {}
    for linha in linhas[1:fim]:
        texto = linha.strip()
        if not texto or texto.startswith("#"):
            continue
        chave, separador, valor = texto.partition(":")
        if not separador:
            raise ErroMarcoInvalido(
                f"Linha do bloco de identificação sem ':' — {texto!r}.",
                sugestao="Cada linha do bloco é 'chave: valor'.",
            )
        metadados[normalizar_nome_de_secao(chave)] = valor.strip()

    return metadados, "\n".join(linhas[fim + 1 :])


def separar_secoes(corpo: str) -> tuple[dict[str, str], dict[str, str]]:
    """Divide o corpo pelos cabeçalhos `## nome`.

    Devolve (seções normalizadas → texto, normalizado → título como escrito).
    Texto antes do primeiro cabeçalho é nota de quem escreve e é ignorado.
    """
    marcas = list(PADRAO_CABECALHO.finditer(corpo))
    secoes: dict[str, str] = {}
    titulos: dict[str, str] = {}

    for indice, marca in enumerate(marcas):
        fim = marcas[indice + 1].start() if indice + 1 < len(marcas) else len(corpo)
        nome = normalizar_nome_de_secao(marca.group(1))
        secoes[nome] = corpo[marca.end() : fim].strip()
        titulos[nome] = marca.group(1).strip()

    return secoes, titulos


def analisar(conteudo: str, identificador: str, caminho: Path | None = None) -> Marco:
    """Texto do arquivo → `Marco`, ou erro que diz o que corrigir e onde."""
    onde = f" em {caminho.name}" if caminho else ""
    metadados, corpo = separar_frontmatter(conteudo)

    faltando = [campo for campo in CAMPOS_OBRIGATORIOS if not metadados.get(campo)]
    if faltando:
        raise ErroMarcoInvalido(
            f"Falta{'m' if len(faltando) > 1 else ''} no bloco de identificação{onde}: {', '.join(faltando)}.",
            sugestao=f"Acrescente {' e '.join(f'{c}: ...' for c in faltando)} entre os '---'.",
        )

    secoes, titulos = separar_secoes(corpo)

    ausentes = [nome for nome in SECOES_OBRIGATORIAS if nome not in secoes]
    if ausentes:
        encontradas = ", ".join(secoes) or "nenhuma"
        raise ErroMarcoInvalido(
            f"Falta{'m' if len(ausentes) > 1 else ''} a seção obrigatória{onde}: {', '.join(ausentes)}.",
            sugestao=f"Seções encontradas: {encontradas}. Acrescente '## {ausentes[0]}' com o texto correspondente.",
        )

    vazias = [nome for nome in SECOES_OBRIGATORIAS if not secoes[nome]]
    if vazias:
        raise ErroMarcoInvalido(
            f"Seção obrigatória vazia{onde}: {', '.join(vazias)}.",
            sugestao="Escreva o texto abaixo do cabeçalho, ou remova a seção se ela não se aplica.",
        )

    return Marco(
        identificador=identificador,
        nome=metadados["nome"],
        versao=metadados["versao"],
        autoria=metadados["autoria"],
        metadados=metadados,
        secoes=secoes,
        titulos=titulos,
        caminho=caminho,
    )


# ── acesso ao diretório ───────────────────────────────────────────────────


def listar(pasta: Path) -> list[str]:
    """Identificadores dos marcos disponíveis, em ordem alfabética."""
    if not pasta.is_dir():
        return []
    return sorted(c.stem for c in pasta.glob("*.md") if c.stem not in NOMES_IGNORADOS)


def carregar(identificador: str, pasta: Path) -> Marco:
    """Lê um marco pelo identificador (nome do arquivo sem `.md`)."""
    caminho = pasta / f"{identificador}.md"

    if not caminho.is_file():
        disponiveis = listar(pasta)
        raise ErroMarcoInvalido(
            f"Marco '{identificador}' não existe em {pasta}.",
            sugestao=(
                f"Disponíveis: {', '.join(disponiveis)}."
                if disponiveis
                else f"Nenhum marco em {pasta} — o repositório traz 'generico' e 'freiriano'."
            ),
        )

    return analisar(caminho.read_text(encoding="utf-8"), identificador, caminho)
