"""
Estruturas de dados do domínio.

São `dataclass` sem comportamento de propósito: as etapas trocam dados por
essas estruturas, então elas precisam ser triviais de serializar, comparar e
construir em teste.
"""

from dataclasses import dataclass, field
from enum import StrEnum


@dataclass(frozen=True, slots=True)
class Chunk:
    """Um trecho de documento, com a proveniência necessária pra citar a fonte.

    Os cinco primeiros campos são o núcleo, presente desde sempre. Os demais são
    a proveniência que `docs/plano/fase-1-corpus.md` §4.7 exige — "cada chunk carrega
    documento de origem, página, offset (…) é a decisão de ingestão que mais dói
    se for esquecida, porque exige reprocessar tudo". Eles existem agora, com
    valor neutro, para que a estratégia de corte por seção e a troca para o
    acervo do IPF não precisem de outra migração de formato depois.

    O corpus de teste é uma wiki: não tem página, e o corte por parágrafo não
    registra offset. Por isso os campos nascem vazios, e quem os preenche é a
    estratégia de corte sensível à estrutura, quando ela entrar.
    """

    chunk_id: str  # "documento::índice" — único e legível
    texto: str
    documento_origem: str  # nome do arquivo de origem
    titulo_pagina: str  # título do artigo (a "página" do corpus)
    chunk_index: int  # posição dentro do documento

    pagina: int = 0  # página no documento original; 0 = não se aplica
    secao: str = ""  # caminho da seção, ex. "Mythology › Altmer"
    inicio: int = 0  # offset em caracteres no corpo do documento
    fim: int = 0
    versao_embedding: str = ""  # modelo que gerou o vetor deste chunk
    restricao_uso: str = ""  # vazio = público; usado como filtro dentro da query

    def como_dicionario(self) -> dict:
        """Serialização usada no JSONL e no payload do banco vetorial.

        Escrita à mão em vez de `dataclasses.asdict` porque este formato é um
        contrato entre etapas: se um campo for renomeado, o índice existente
        continua legível e a quebra aparece aqui, num lugar só.

        Campo em branco não é gravado. Não é economia de bytes: é o que faz o
        `chunks.jsonl` do corpus atual continuar byte a byte idêntico ao de
        antes destes campos existirem, e o payload dos pontos já indexados
        continuar igual ao de um ponto novo. Acrescentar proveniência não pode
        custar horas de reindexação.
        """
        dados = {
            "chunk_id": self.chunk_id,
            "texto": self.texto,
            "documento_origem": self.documento_origem,
            "titulo_pagina": self.titulo_pagina,
            "chunk_index": self.chunk_index,
        }

        opcionais = {
            "pagina": self.pagina,
            "secao": self.secao,
            "inicio": self.inicio,
            "fim": self.fim,
            "versao_embedding": self.versao_embedding,
            "restricao_uso": self.restricao_uso,
        }
        dados.update({chave: valor for chave, valor in opcionais.items() if valor})
        return dados

    @classmethod
    def de_dicionario(cls, dados: dict) -> "Chunk":
        """Lê o formato atual e o anterior — os campos novos vêm com `.get`."""
        return cls(
            chunk_id=dados["chunk_id"],
            texto=dados["texto"],
            documento_origem=dados["documento_origem"],
            titulo_pagina=dados["titulo_pagina"],
            chunk_index=int(dados["chunk_index"]),
            pagina=int(dados.get("pagina", 0)),
            secao=dados.get("secao", ""),
            inicio=int(dados.get("inicio", 0)),
            fim=int(dados.get("fim", 0)),
            versao_embedding=dados.get("versao_embedding", ""),
            restricao_uso=dados.get("restricao_uso", ""),
        )


@dataclass(frozen=True, slots=True)
class TrechoRecuperado:
    """Resultado de uma busca — o chunk mais a pontuação de similaridade."""

    texto: str
    titulo_pagina: str
    documento_origem: str
    chunk_id: str
    score: float

    def previa(self, limite: int = 150) -> str:
        """Trecho em uma linha, pra listagem compacta no console."""
        texto = " ".join(self.texto.split())
        return texto[:limite] + ("..." if len(texto) > limite else "")


@dataclass(frozen=True, slots=True)
class Resposta:
    """Resposta gerada com os trechos que a fundamentaram."""

    pergunta: str
    texto: str
    trechos: list[TrechoRecuperado]
    segundos: float


@dataclass
class ResultadoEtapa:
    """Contadores de uma etapa, pra interface relatar sem inventar formato.

    `falhas` guarda as mensagens de lote que falharam: o pipeline segue em
    frente quando um lote quebra, mas o usuário precisa saber que seguiu.
    """

    processados: int = 0
    ignorados: int = 0
    falhas: list[str] = field(default_factory=list)
    detalhes: dict = field(default_factory=dict)

    @property
    def houve_falha(self) -> bool:
        return bool(self.falhas)


# ── sessão dialógica ──────────────────────────────────────────────────────


class TipoDeDemanda(StrEnum):
    """Os três tipos de demanda que a triagem distingue.

    Vêm dos documentos de origem (`docs/plano/fase-3-avaliacao-e-servidor.md` §4), onde
    são campo obrigatório dos casos-teste. A dúvida factual atalha direto para a
    busca; as outras duas passam pela problematização.
    """

    PRODUTO_ACABADO = "produto_acabado"
    DUVIDA_FACTUAL = "duvida_factual"
    EXPLORACAO = "exploracao"
    INDEFINIDO = "indefinido"


class EstadoDaSessao(StrEnum):
    """Onde a conversa está."""

    TRIAGEM = "triagem"
    PROBLEMATIZACAO = "problematizacao"
    RECUPERACAO = "recuperacao"
    RESPOSTA = "resposta"
    ENCERRADA = "encerrada"


@dataclass(frozen=True, slots=True)
class TrocaDaConversa:
    """Uma pergunta respondida, guardada para a seguinte entender o contexto.

    `pergunta` é como a pessoa escreveu; `consulta` é a versão autônoma que foi
    à busca. A reescrita da próxima pergunta usa a consulta, que já resolveu as
    referências — reescrever a partir da pergunta crua acumularia ambiguidade.
    """

    pergunta: str
    consulta: str
    resposta: str = ""


@dataclass(frozen=True, slots=True)
class Turno:
    """Uma fala, de quem pergunta ou do sistema."""

    autor: str  # "pessoa" | "sistema"
    texto: str
    estado: EstadoDaSessao


@dataclass
class Sessao:
    """O estado de uma conversa.

    Mutável de propósito: é a única estrutura do domínio que muda ao longo do
    tempo, e é o que a máquina de estados em `rag.sessao` avança.
    """

    pergunta_inicial: str
    estado: EstadoDaSessao = EstadoDaSessao.TRIAGEM
    demanda: TipoDeDemanda = TipoDeDemanda.INDEFINIDO
    turnos: list[Turno] = field(default_factory=list)
    rodadas_de_problematizacao: int = 0

    def registrar(self, autor: str, texto: str) -> None:
        self.turnos.append(Turno(autor=autor, texto=texto, estado=self.estado))

    def respostas_da_pessoa(self) -> list[str]:
        """O que a pessoa respondeu à problematização — só isso."""
        return [
            turno.texto
            for turno in self.turnos
            if turno.autor == "pessoa" and turno.estado is EstadoDaSessao.PROBLEMATIZACAO
        ]

    def perguntas_devolvidas(self) -> list[str]:
        return [turno.texto for turno in self.turnos if turno.autor == "sistema"]

    def consulta_consolidada(self) -> str:
        """O texto que vai à recuperação: a demanda mais o que a pessoa disse.

        As perguntas que o sistema devolveu ficam de fora de propósito. Elas são
        vocabulário do próprio sistema, e pô-las na consulta puxaria a busca
        para os termos que ele acabou de escolher, em vez dos termos de quem
        pergunta — o embedding acabaria buscando o eco da máquina.
        """
        return "\n".join([self.pergunta_inicial, *self.respostas_da_pessoa()])
