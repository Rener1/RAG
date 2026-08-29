"""
Etapa 3 — embedding e indexação.

Lê `data/chunks.jsonl`, gera o vetor de cada chunk e grava no banco vetorial
junto com o payload de proveniência. Embedding e indexação são a mesma etapa
na prática: vetor sem lugar onde ser buscado não serve para nada.

É a etapa cara — horas de processamento local no corpus inteiro. Daí as três
proteções que ela ganhou:

1. **Retomada.** Chunks já indexados são pulados por padrão, então uma
   execução interrompida continua de onde parou em vez de refazer tudo.
2. **Validação de dimensão antes de começar**, no lugar de descobrir a
   incompatibilidade lote a lote, depois de já ter gasto processamento.
3. **Submissão em janela.** Os lotes são enviados ao pool aos poucos; a versão
   anterior criava um `Future` por lote de uma vez só (milhares deles, com o
   conteúdo dos chunks preso na memória até o fim da execução).
"""

import json
from collections.abc import Iterator
from pathlib import Path

from ..config import ConfigEmbedding
from ..erros import ErroPreRequisito
from ..modelos import Chunk, ResultadoEtapa
from ..protocolos import Embutidor, RepositorioVetorial
from . import RelatorProgresso, sem_progresso

# Quantos chunk_ids são conferidos por consulta ao banco, ao verificar o que
# já está indexado. Alto o bastante para poucas viagens, baixo o bastante para
# a requisição não estourar.
TAMANHO_CONSULTA_EXISTENTES = 1000


def contar_chunks(arquivo: Path) -> int:
    """Total de linhas do JSONL, para a barra de progresso ter denominador."""
    with arquivo.open("rb") as f:
        return sum(1 for linha in f if linha.strip())


def ler_chunks(arquivo: Path) -> Iterator[Chunk]:
    """Lê o JSONL preguiçosamente — o arquivo tem dezenas de MB."""
    with arquivo.open(encoding="utf-8") as f:
        for numero, linha in enumerate(f, start=1):
            linha = linha.strip()
            if not linha:
                continue
            try:
                yield Chunk.de_dicionario(json.loads(linha))
            except (json.JSONDecodeError, KeyError) as erro:
                raise ErroPreRequisito(
                    f"Linha {numero} de {arquivo.name} está corrompida: {erro}",
                    sugestao="Rode a etapa de chunking de novo para regerar o arquivo.",
                ) from erro


def agrupar(itens: Iterator[Chunk], tamanho: int) -> Iterator[list[Chunk]]:
    """Fatia um fluxo de chunks em lotes de tamanho fixo."""
    lote: list[Chunk] = []
    for item in itens:
        lote.append(item)
        if len(lote) >= tamanho:
            yield lote
            lote = []
    if lote:
        yield lote


def filtrar_ja_indexados(
    lotes: Iterator[list[Chunk]],
    repositorio: RepositorioVetorial,
    ao_pular: callable,
) -> Iterator[list[Chunk]]:
    """Remove dos lotes os chunks que o índice já tem.

    Junta vários lotes antes de perguntar ao banco: uma consulta por lote de
    16 seria mais viagem de rede do que trabalho economizado.
    """
    acumulado: list[list[Chunk]] = []
    quantidade = 0

    def liberar() -> Iterator[list[Chunk]]:
        nonlocal acumulado, quantidade
        if not acumulado:
            return
        todos = [chunk for lote in acumulado for chunk in lote]
        existentes = repositorio.ids_existentes([c.chunk_id for c in todos])
        for lote in acumulado:
            pendentes = [c for c in lote if c.chunk_id not in existentes]
            pulados = len(lote) - len(pendentes)
            if pulados:
                ao_pular(pulados)
            if pendentes:
                yield pendentes
        acumulado, quantidade = [], 0

    for lote in lotes:
        acumulado.append(lote)
        quantidade += len(lote)
        if quantidade >= TAMANHO_CONSULTA_EXISTENTES:
            yield from liberar()
    yield from liberar()


def executar(
    config: ConfigEmbedding,
    embutidor: Embutidor,
    repositorio: RepositorioVetorial,
    arquivo_chunks: Path,
    *,
    retomar: bool = True,
    recriar_colecao: bool = False,
    progresso: RelatorProgresso = sem_progresso,
) -> ResultadoEtapa:
    """Indexa o arquivo de chunks inteiro.

    `retomar=True` pula o que já está indexado. `recriar_colecao=True` apaga a
    coleção antes — necessário ao trocar de modelo de embedding.
    """
    from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

    if not arquivo_chunks.exists():
        raise ErroPreRequisito(
            f"{arquivo_chunks} não existe.",
            sugestao="Rode a etapa de chunking antes desta.",
        )

    # Antes de qualquer processamento: a coleção precisa aceitar estes vetores.
    repositorio.garantir_colecao(embutidor.dimensao, recriar=recriar_colecao)

    total = contar_chunks(arquivo_chunks)
    resultado = ResultadoEtapa()
    resultado.detalhes = {"total_de_chunks": total, "colecao": getattr(repositorio, "colecao", "?")}

    def registrar_pulados(quantidade: int) -> None:
        resultado.ignorados += quantidade

    lotes = agrupar(ler_chunks(arquivo_chunks), config.tamanho_lote)
    if retomar and not recriar_colecao:
        lotes = filtrar_ja_indexados(lotes, repositorio, registrar_pulados)

    def indexar(lote: list[Chunk]) -> int:
        vetores = embutidor.embutir([c.texto for c in lote])
        return repositorio.inserir(lote, vetores)

    # Janela de submissão: mantém o pool alimentado sem materializar todos os
    # lotes de uma vez.
    janela = max(config.lotes_paralelos * 2, 4)

    with ThreadPoolExecutor(max_workers=config.lotes_paralelos) as executor:
        pendentes: set = set()
        fonte = iter(lotes)
        acabou = False

        while not acabou or pendentes:
            while not acabou and len(pendentes) < janela:
                try:
                    pendentes.add(executor.submit(indexar, next(fonte)))
                except StopIteration:
                    acabou = True

            if not pendentes:
                break

            concluidos, pendentes = wait(pendentes, return_when=FIRST_COMPLETED)
            for futuro in concluidos:
                try:
                    resultado.processados += futuro.result()
                except Exception as erro:
                    # Um lote que falha não derruba a execução: o erro é
                    # registrado e relatado no fim, e repetir a etapa recupera
                    # o que faltou (a gravação é idempotente por chunk_id).
                    resultado.falhas.append(str(erro))

            progresso(resultado.processados + resultado.ignorados, total, f"{resultado.processados} indexados")

    return resultado
