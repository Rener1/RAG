"""
Estruturas de dados do domínio.

São `dataclass` sem comportamento de propósito: as etapas trocam dados por
essas estruturas, então elas precisam ser triviais de serializar, comparar e
construir em teste.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Chunk:
    """Um trecho de documento, com a proveniência necessária pra citar a fonte."""

    chunk_id: str  # "documento::índice" — único e legível
    texto: str
    documento_origem: str  # nome do arquivo de origem
    titulo_pagina: str  # título do artigo (a "página" do corpus)
    chunk_index: int  # posição dentro do documento

    def como_dicionario(self) -> dict:
        """Serialização usada no JSONL e no payload do banco vetorial.

        Escrita à mão em vez de `dataclasses.asdict` porque este formato é um
        contrato entre etapas: se um campo for renomeado, o índice existente
        continua legível e a quebra aparece aqui, num lugar só.
        """
        return {
            "chunk_id": self.chunk_id,
            "texto": self.texto,
            "documento_origem": self.documento_origem,
            "titulo_pagina": self.titulo_pagina,
            "chunk_index": self.chunk_index,
        }

    @classmethod
    def de_dicionario(cls, dados: dict) -> "Chunk":
        return cls(
            chunk_id=dados["chunk_id"],
            texto=dados["texto"],
            documento_origem=dados["documento_origem"],
            titulo_pagina=dados["titulo_pagina"],
            chunk_index=int(dados["chunk_index"]),
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
