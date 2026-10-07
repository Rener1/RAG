"""
Contratos das peças substituíveis.

O pedido de modularidade é concreto: trocar o banco vetorial, o modelo de
embedding ou o gerador não pode obrigar a mexer nas outras etapas. Esses
`Protocol` são a fronteira onde essa troca acontece — as etapas dependem
deles, não das classes concretas em `rag.clientes`.

São `Protocol` (tipagem estrutural) e não classes-base: uma implementação
alternativa não precisa herdar de nada, só ter os métodos com a mesma forma.
"""

from collections.abc import Iterator
from typing import Protocol, runtime_checkable

from .modelos import Chunk, TrechoRecuperado


@runtime_checkable
class Embutidor(Protocol):
    """Transforma texto em vetor. Implementação atual: Ollama com bge-m3."""

    @property
    def dimensao(self) -> int:
        """Tamanho do vetor produzido — a coleção é criada com esse valor."""
        ...

    def embutir(self, textos: list[str]) -> list[list[float]]:
        """Um vetor por texto, na mesma ordem. Erra alto se a contagem não bater."""
        ...


@runtime_checkable
class Gerador(Protocol):
    """Produz texto a partir de um prompt. Implementação atual: Ollama."""

    def gerar(self, prompt: str) -> Iterator[str]:
        """Devolve a resposta em pedaços, para poder imprimir conforme sai."""
        ...


@runtime_checkable
class RepositorioVetorial(Protocol):
    """Armazena e busca vetores. Implementação atual: Qdrant.

    Trocar por outro banco (pgvector, Chroma...) é escrever outra classe com
    esses métodos e injetá-la — nenhuma etapa precisa saber da troca.
    """

    def garantir_colecao(self, dimensao: int, recriar: bool = False) -> None: ...

    def contar_pontos(self) -> int: ...

    def dimensao_da_colecao(self) -> int | None:
        """`None` quando a coleção ainda não existe."""
        ...

    def ids_existentes(self, chunk_ids: list[str]) -> set[str]:
        """Quais desses chunks já estão indexados — permite retomar sem refazer."""
        ...

    def inserir(self, chunks: list[Chunk], vetores: list[list[float]]) -> int: ...

    def buscar(self, vetor: list[float], k: int, score_minimo: float = 0.0) -> list[TrechoRecuperado]: ...


@runtime_checkable
class ColetorDeCorpus(Protocol):
    """Traz documentos de uma fonte externa. Implementação atual: API da UESP.

    Trocar o corpus de teste pelo acervo real do IPF é escrever outro coletor
    com estes métodos — a etapa de download não muda.
    """

    def descobrir_namespace(self) -> int: ...

    def listar_titulos(self, namespace_id: int, limite: int) -> list[str]: ...

    def baixar_lote(self, titulos: list[str]) -> dict[str, str]:
        """Título → conteúdo bruto, para os títulos que existem."""
        ...


@runtime_checkable
class Reordenador(Protocol):
    """Reordena candidatos pela relevância real à pergunta.

    A busca vetorial compara dois vetores calculados em separado; um
    cross-encoder lê pergunta e trecho **juntos**, e por isso julga melhor — ao
    custo de não dar para pré-calcular, o que o limita a reordenar um punhado de
    candidatos em vez de varrer o acervo.

    A etapa de recuperação depende disto, e não da classe concreta: trocar o
    modelo de reordenação é escrever outra classe com este método.
    """

    def reordenar(self, pergunta: str, trechos: list[TrechoRecuperado]) -> list[TrechoRecuperado]:
        """Os mesmos trechos, do mais para o menos relevante."""
        ...


@runtime_checkable
class RecuperadorDeTrechos(Protocol):
    """Devolve os trechos mais relevantes para uma pergunta.

    O orquestrador depende disto, e não da classe `Recuperador`: é o que
    permite pôr uma decomposição de consulta na frente da busca sem alterar o
    ciclo RAG.
    """

    def buscar(self, pergunta: str, k: int | None = None) -> list[TrechoRecuperado]: ...


@runtime_checkable
class MarcoPedagogico(Protocol):
    """O documento que define como o sistema se comporta.

    A etapa de geração depende disto, e não da classe `Marco`: o marco vive em
    arquivo versionado fora do código (`docs/plano/fase-0-desenho-e-contratos.md` §3.5),
    e a etapa não precisa saber de onde ele veio nem como foi analisado.
    """

    @property
    def identificador(self) -> str: ...

    def secao(self, nome: str, padrao: str = "") -> str: ...

    def metadado(self, nome: str, padrao: str = "") -> str:
        """Um campo do bloco de identificação do marco."""
        ...

    def secoes_de_resposta(self) -> list[tuple[str, str]]:
        """(título, texto) das seções que orientam a resposta, na ordem do prompt.

        Quais seções são essas é decisão do marco, não da geração — é o que
        permite ao comitê acrescentar uma seção sem que ninguém mexa em código.
        """
        ...
