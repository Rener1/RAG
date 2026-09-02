"""
Apoio comum aos testes: caminho de import e dublês das dependências externas.

Os dublês existem para que os testes rodem sem Qdrant, sem Ollama e sem rede —
o que é o ponto da modularidade: as etapas dependem dos protocolos, então uma
implementação de mentira serve tão bem quanto a real.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rag.modelos import Chunk, TrechoRecuperado  # noqa: E402


class EmbutidorFalso:
    """Vetores determinísticos, sem chamar o Ollama."""

    def __init__(self, dimensao: int = 4) -> None:
        self._dimensao = dimensao
        self.chamadas: list[list[str]] = []

    @property
    def dimensao(self) -> int:
        return self._dimensao

    def embutir(self, textos: list[str]) -> list[list[float]]:
        self.chamadas.append(list(textos))
        return [[float(len(t) % 7), 1.0, 0.0, 0.5] for t in textos]


class EmbutidorPorTexto:
    """Um vetor por texto distinto, ortogonais entre si salvo quando ditado.

    `EmbutidorFalso` não serve para exercitar a deduplicação: os vetores dele
    dependem só de `len(texto) % 7`, então dois textos sem relação nenhuma saem
    quase paralelos e a dedup os confundiria. Aqui textos diferentes são
    ortogonais por construção (cosseno 0) e textos iguais são idênticos — que é
    o comportamento neutro que os testes de mediação querem de pano de fundo.

    `vetores` dita o vetor de textos específicos, para montar redundância de
    propósito.
    """

    DIMENSAO = 32

    def __init__(self, vetores: dict[str, list[float]] | None = None) -> None:
        self._ditados = vetores or {}
        self._atribuidos: dict[str, list[float]] = {}
        self.chamadas: list[list[str]] = []
        self.erro: Exception | None = None

    @property
    def dimensao(self) -> int:
        return self.DIMENSAO

    def _vetor(self, texto: str) -> list[float]:
        if texto in self._ditados:
            return list(self._ditados[texto])
        if texto not in self._atribuidos:
            posicao = len(self._atribuidos) % self.DIMENSAO
            vetor = [0.0] * self.DIMENSAO
            vetor[posicao] = 1.0
            self._atribuidos[texto] = vetor
        return list(self._atribuidos[texto])

    def embutir(self, textos: list[str]) -> list[list[float]]:
        self.chamadas.append(list(textos))
        if self.erro is not None:
            raise self.erro
        return [self._vetor(t) for t in textos]


class RepositorioFalso:
    """Banco vetorial em memória, com a mesma forma do RepositorioQdrant."""

    def __init__(self, dimensao_existente: int | None = None) -> None:
        self.pontos: dict[str, Chunk] = {}
        self.dimensao_existente = dimensao_existente
        self.recriado = False
        self.colecao = "teste"

    def garantir_colecao(self, dimensao: int, recriar: bool = False) -> None:
        if recriar:
            self.pontos.clear()
            self.recriado = True
        self.dimensao_existente = dimensao

    def contar_pontos(self) -> int:
        return len(self.pontos)

    def dimensao_da_colecao(self) -> int | None:
        return self.dimensao_existente

    def ids_existentes(self, chunk_ids: list[str]) -> set[str]:
        return {c for c in chunk_ids if c in self.pontos}

    def inserir(self, chunks: list[Chunk], vetores: list[list[float]]) -> int:
        for chunk, _ in zip(chunks, vetores, strict=True):
            self.pontos[chunk.chunk_id] = chunk
        return len(chunks)

    def buscar(self, vetor: list[float], k: int, score_minimo: float = 0.0) -> list[TrechoRecuperado]:
        return [
            TrechoRecuperado(
                texto=chunk.texto,
                titulo_pagina=chunk.titulo_pagina,
                documento_origem=chunk.documento_origem,
                chunk_id=chunk.chunk_id,
                score=0.9,
            )
            for chunk in list(self.pontos.values())[:k]
        ]


class GeradorFalso:
    """Devolve o prompt recebido em pedaços — permite inspecionar o que foi montado."""

    def __init__(self) -> None:
        self.ultimo_prompt = ""

    def gerar(self, prompt: str):
        self.ultimo_prompt = prompt
        yield "resposta "
        yield "gerada"


class GeradorRoteirizado:
    """Uma resposta por chamada, na ordem escrita. Guarda todos os prompts.

    Existe para testar as chamadas internas (reformulação, triagem,
    problematização), que precisam de uma saída controlada e de conferir o que
    foi perguntado ao modelo. `GeradorFalso` devolve sempre a mesma coisa e
    continua servindo para a geração da resposta.
    """

    def __init__(self, respostas: list[str] | None = None, erro: Exception | None = None) -> None:
        self.respostas = list(respostas or [])
        self.erro = erro
        self.prompts: list[str] = []

    def gerar(self, prompt: str):
        self.prompts.append(prompt)
        if self.erro is not None:
            raise self.erro
        yield self.respostas.pop(0) if self.respostas else ""


class RecuperadorFalso:
    """Cumpre `RecuperadorDeTrechos`. Ranking por consulta; registra o recebido."""

    def __init__(
        self,
        por_consulta: dict[str, list[TrechoRecuperado]] | None = None,
        padrao: list[TrechoRecuperado] | None = None,
    ) -> None:
        self.por_consulta = por_consulta or {}
        self.padrao = padrao or []
        self.consultas: list[tuple[str, int | None]] = []

    def buscar(self, pergunta: str, k: int | None = None) -> list[TrechoRecuperado]:
        self.consultas.append((pergunta, k))
        return self.por_consulta.get(pergunta, self.padrao)


class ReordenadorFalso:
    """Cumpre `Reordenador` sem carregar modelo nenhum.

    Reordena pela ordem ditada em `preferencia` (títulos de página); o que não
    estiver lá mantém a posição relativa. Permite testar a fiação da reordenação
    sem `torch`, que é o que mantém a suíte rodando sem dependência pesada.
    """

    def __init__(self, preferencia: list[str] | None = None, erro: Exception | None = None) -> None:
        self.preferencia = preferencia or []
        self.erro = erro
        self.chamadas: list[tuple[str, int]] = []

    def reordenar(self, pergunta: str, trechos: list[TrechoRecuperado]) -> list[TrechoRecuperado]:
        self.chamadas.append((pergunta, len(trechos)))
        if self.erro is not None:
            raise self.erro

        def posicao(trecho: TrechoRecuperado) -> int:
            if trecho.titulo_pagina in self.preferencia:
                return self.preferencia.index(trecho.titulo_pagina)
            return len(self.preferencia)

        return sorted(trechos, key=posicao)


class MarcoFalso:
    """Cumpre `MarcoPedagogico` sem tocar em disco."""

    def __init__(
        self,
        secoes: dict[str, str] | None = None,
        identificador: str = "falso",
        metadados: dict[str, str] | None = None,
    ) -> None:
        self._identificador = identificador
        self.secoes = secoes or {"Papel": "papel de teste", "Instruções": "instruções de teste"}
        self.metadados = metadados or {}

    @property
    def identificador(self) -> str:
        return self._identificador

    def secao(self, nome: str, padrao: str = "") -> str:
        return self.secoes.get(nome, padrao)

    def metadado(self, nome: str, padrao: str = "") -> str:
        return self.metadados.get(nome, padrao)

    def diz_sim(self, nome: str, padrao: bool) -> bool:
        valor = self.metadados.get(nome, "").strip().casefold()
        return padrao if not valor else valor in {"sim", "s", "true", "1", "yes"}

    def secoes_de_resposta(self) -> list[tuple[str, str]]:
        return list(self.secoes.items())


class ColetorFalso:
    """Wiki de mentira, para testar a etapa de download sem tocar na rede."""

    def __init__(self, paginas: dict[str, str]) -> None:
        self.paginas = paginas
        self.lotes_pedidos: list[list[str]] = []

    def descobrir_namespace(self) -> int:
        return 130

    def listar_titulos(self, namespace_id: int, limite: int) -> list[str]:
        return list(self.paginas)[:limite]

    def baixar_lote(self, titulos: list[str]) -> dict[str, str]:
        self.lotes_pedidos.append(list(titulos))
        return {t: self.paginas[t] for t in titulos if t in self.paginas}
