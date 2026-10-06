"""
Camada 4 — avaliação da recuperação.

`docs/fase-3-avaliacao-e-servidor.md` §7 separa as métricas por camada e avisa
por quê: **"não misturar: recuperação ruim e geração ruim têm correções
opostas"**. Aqui mora só a recuperação — automática e barata, para rodar a cada
mudança de chunking, embedding, `k` ou mediação.

A qualidade da resposta gerada **não é medida aqui, e não por esquecimento**. O
modo de falha que importa é a produção de "freirês" — vocabulário militante bem
articulado, aplicado sem ancoragem no território concreto — e o doc é explícito
em que ele é invisível para métrica automática (§3), e em que um LLM julgando
aderência tende a premiar exatamente esse texto (§8). Essa camada é rubrica
humana, e não entra em código.

Mora na raiz do pacote, como `orquestrador.py` e `mediacao.py`: compõe a
recuperação com um artefato versionado, o que não pertence a nenhuma etapa.
Depende de `RecuperadorDeTrechos`, nunca de `Recuperador` — é o que permite
medir a busca direta e a mediada com exatamente o mesmo código.
"""

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .erros import ErroConfiguracao
from .etapas import RelatorProgresso, sem_progresso
from .modelos import TrechoRecuperado
from .protocolos import RecuperadorDeTrechos

# Campos exigidos de cada caso. Os nomes vêm da tabela de `fase-3` §4, para o
# conjunto real do comitê entrar neste mesmo harness sem reescrever nada.
CAMPOS_OBRIGATORIOS = ("id", "demanda", "paginas_esperadas")

TIPOS_DE_DEMANDA = ("duvida_factual", "exploracao", "produto_acabado")


@dataclass(frozen=True, slots=True)
class CasoDeTeste:
    identificador: str
    demanda: str
    paginas_esperadas: tuple[str, ...]
    tipo_de_demanda: str = "indefinido"
    observacao: str = ""


def _paginas_em_ordem(trechos: list[TrechoRecuperado]) -> tuple[str, ...]:
    """Páginas na ordem em que apareceram, sem repetir.

    Dois trechos da mesma página não são dois acertos, e a posição que
    interessa é a da primeira.
    """
    paginas: list[str] = []
    for trecho in trechos:
        if trecho.titulo_pagina not in paginas:
            paginas.append(trecho.titulo_pagina)
    return tuple(paginas)


@dataclass(frozen=True, slots=True)
class ResultadoDeCaso:
    caso: CasoDeTeste
    paginas_recuperadas: tuple[str, ...]
    trechos_recuperados: int = 0
    # O que sobra depois do orçamento de contexto. `None` = não medido (a
    # avaliação rodou sem orçamento), e aí tudo o que foi recuperado conta.
    paginas_no_prompt: tuple[str, ...] | None = None
    trechos_no_prompt: int | None = None

    @property
    def acertos(self) -> int:
        """Quantas das páginas esperadas apareceram no top-k."""
        return sum(1 for pagina in self.caso.paginas_esperadas if pagina in self.paginas_recuperadas)

    @property
    def acertou(self) -> bool:
        return self.acertos > 0

    @property
    def foi_cortado(self) -> bool:
        """O orçamento de contexto descartou algum trecho recuperado."""
        return self.trechos_no_prompt is not None and self.trechos_no_prompt < self.trechos_recuperados

    @property
    def acertou_no_prompt(self) -> bool:
        """Acerto que de fato chegaria ao modelo."""
        paginas = self.paginas_recuperadas if self.paginas_no_prompt is None else self.paginas_no_prompt
        return any(pagina in paginas for pagina in self.caso.paginas_esperadas)

    @property
    def posicao_do_primeiro_acerto(self) -> int | None:
        """Posição 1-based da primeira página esperada. `None` se não veio nenhuma."""
        for posicao, pagina in enumerate(self.paginas_recuperadas, start=1):
            if pagina in self.caso.paginas_esperadas:
                return posicao
        return None

    @property
    def cobertura(self) -> float:
        """Fração das páginas esperadas que foram recuperadas."""
        if not self.caso.paginas_esperadas:
            return 0.0
        return self.acertos / len(self.caso.paginas_esperadas)


@dataclass(frozen=True, slots=True)
class ResultadoDaAvaliacao:
    resultados: list[ResultadoDeCaso]
    k: int | None  # None = quantidade dinâmica, decidida pela política de busca
    segundos: float
    rotulo: str = ""

    @property
    def descricao_do_k(self) -> str:
        return f"@{self.k}" if self.k is not None else " (k dinâmico)"

    @property
    def trechos_por_caso(self) -> float:
        """Média de trechos recuperados. Só varia quando a quantidade é dinâmica.

        Resultados montados sem a contagem de trechos caem na de páginas.
        """
        if not self.resultados:
            return 0.0
        return sum(r.trechos_recuperados or len(r.paginas_recuperadas) for r in self.resultados) / len(self.resultados)

    @property
    def mediu_orcamento(self) -> bool:
        return any(r.trechos_no_prompt is not None for r in self.resultados)

    @property
    def casos_cortados(self) -> int:
        """Casos em que o orçamento de contexto descartou trecho recuperado."""
        return sum(1 for r in self.resultados if r.foi_cortado)

    @property
    def recall_no_prompt(self) -> float:
        """Recall contado só sobre o que cabe no prompt — o que o modelo veria."""
        if not self.resultados:
            return 0.0
        return sum(1 for r in self.resultados if r.acertou_no_prompt) / len(self.resultados)

    @property
    def total(self) -> int:
        return len(self.resultados)

    @property
    def recall(self) -> float:
        """Fração dos casos com pelo menos uma página esperada no top-k."""
        if not self.resultados:
            return 0.0
        return sum(1 for r in self.resultados if r.acertou) / len(self.resultados)

    @property
    def cobertura_media(self) -> float:
        """Média da fração de páginas esperadas encontradas por caso.

        Distinta de `recall`: um caso que espera três páginas e traz uma conta
        como acerto no `recall` e como um terço aqui. É o que separa "achou
        alguma coisa" de "achou o que precisava".
        """
        if not self.resultados:
            return 0.0
        return sum(r.cobertura for r in self.resultados) / len(self.resultados)

    @property
    def mrr(self) -> float:
        """Média do inverso da posição do primeiro acerto.

        Sensível a ordem, ao contrário do `recall`: mede se o material certo
        chegou ao topo ou raspou no fim da lista.
        """
        if not self.resultados:
            return 0.0
        return sum(
            1 / r.posicao_do_primeiro_acerto if r.posicao_do_primeiro_acerto else 0.0 for r in self.resultados
        ) / len(self.resultados)

    def por_tipo(self) -> dict[str, tuple[int, float]]:
        """(quantidade, recall) por tipo de demanda.

        Não é enfeite: a hipótese mais provável sobre a mediação é que ela ajude
        nas compostas e atrapalhe nas factuais simples, e uma média global
        esconderia exatamente isso — que é a decisão que se quer tomar.
        """
        agrupado: dict[str, list[ResultadoDeCaso]] = {}
        for resultado in self.resultados:
            agrupado.setdefault(resultado.caso.tipo_de_demanda, []).append(resultado)

        return {
            tipo: (len(casos), sum(1 for c in casos if c.acertou) / len(casos))
            for tipo, casos in sorted(agrupado.items())
        }

    def por_identificador(self) -> dict[str, ResultadoDeCaso]:
        return {r.caso.identificador: r for r in self.resultados}


def carregar_casos(caminho: Path) -> list[CasoDeTeste]:
    """Lê o gabarito. Erro nomeia a linha, para o conserto ser óbvio."""
    if not caminho.exists():
        raise ErroConfiguracao(
            f"Gabarito de avaliação não encontrado: {caminho}",
            sugestao="O conjunto versionado fica em `avaliacao/casos.jsonl`. Use --casos para apontar outro.",
        )

    casos: list[CasoDeTeste] = []
    vistos: set[str] = set()

    for numero, linha in enumerate(caminho.read_text(encoding="utf-8").splitlines(), start=1):
        if not linha.strip():
            continue

        try:
            dados = json.loads(linha)
        except json.JSONDecodeError as erro:
            raise ErroConfiguracao(
                f"{caminho.name}, linha {numero}: JSON inválido ({erro.msg}).",
                sugestao="Cada linha é um objeto JSON completo, sem vírgula no fim.",
            ) from erro

        faltando = [campo for campo in CAMPOS_OBRIGATORIOS if not dados.get(campo)]
        if faltando:
            raise ErroConfiguracao(
                f"{caminho.name}, linha {numero}: falta {', '.join(faltando)}.",
                sugestao=f"Todo caso precisa de {', '.join(CAMPOS_OBRIGATORIOS)}.",
            )

        identificador = str(dados["id"])
        if identificador in vistos:
            raise ErroConfiguracao(
                f"{caminho.name}, linha {numero}: o identificador '{identificador}' aparece duas vezes.",
                sugestao="Os identificadores precisam ser únicos para a comparação entre rodadas casar os casos.",
            )
        vistos.add(identificador)

        casos.append(
            CasoDeTeste(
                identificador=identificador,
                demanda=str(dados["demanda"]),
                paginas_esperadas=tuple(dados["paginas_esperadas"]),
                tipo_de_demanda=str(dados.get("tipo_de_demanda", "indefinido")),
                observacao=str(dados.get("observacao", "")),
            )
        )

    if not casos:
        raise ErroConfiguracao(
            f"{caminho.name} não tem nenhum caso.",
            sugestao="Acrescente ao menos um caso, um objeto JSON por linha.",
        )

    return casos


def avaliar(
    casos: list[CasoDeTeste],
    recuperador: RecuperadorDeTrechos,
    k: int | None,
    rotulo: str = "",
    progresso: RelatorProgresso = sem_progresso,
    ajustar: Callable[[str, list[TrechoRecuperado]], list[TrechoRecuperado]] | None = None,
) -> ResultadoDaAvaliacao:
    """Roda o gabarito contra um recuperador. Não gera texto nenhum.

    `k = None` deixa a quantidade por conta da política de busca configurada —
    é o que permite medir o `k` dinâmico. Passar um número força aquele número,
    que é o que a varredura de `k` precisa.

    `ajustar` é o corte do orçamento de contexto (`MotorRag.trechos_que_cabem`).
    Com ele, cada caso registra também o que chegaria ao modelo: recortes
    maiores ou `k` maior podem recuperar bem e ainda assim não caber na janela.
    """
    inicio = time.monotonic()
    resultados: list[ResultadoDeCaso] = []

    for numero, caso in enumerate(casos, start=1):
        trechos = recuperador.buscar(caso.demanda, k=k)
        no_prompt = ajustar(caso.demanda, trechos) if ajustar else None

        resultados.append(
            ResultadoDeCaso(
                caso=caso,
                paginas_recuperadas=_paginas_em_ordem(trechos),
                trechos_recuperados=len(trechos),
                paginas_no_prompt=_paginas_em_ordem(no_prompt) if no_prompt is not None else None,
                trechos_no_prompt=len(no_prompt) if no_prompt is not None else None,
            )
        )
        progresso(numero, len(casos), caso.identificador)

    return ResultadoDaAvaliacao(
        resultados=resultados,
        k=k,
        segundos=time.monotonic() - inicio,
        rotulo=rotulo,
    )


def comparar(
    antes: ResultadoDaAvaliacao, depois: ResultadoDaAvaliacao
) -> list[tuple[CasoDeTeste, int | None, int | None]]:
    """Casos cuja posição do primeiro acerto mudou, do pior para o melhor.

    Existe para uma regressão ser localizável. Uma média que cai três pontos não
    diz onde consertar; a lista de casos que pioraram, sim.
    """
    de_antes = antes.por_identificador()
    mudancas: list[tuple[CasoDeTeste, int | None, int | None]] = []

    for resultado in depois.resultados:
        anterior = de_antes.get(resultado.caso.identificador)
        if anterior is None:
            continue
        posicao_antes = anterior.posicao_do_primeiro_acerto
        posicao_depois = resultado.posicao_do_primeiro_acerto
        if posicao_antes != posicao_depois:
            mudancas.append((resultado.caso, posicao_antes, posicao_depois))

    # Não achado (None) é o pior desfecho: vai para o topo da lista.
    def gravidade(item: tuple[CasoDeTeste, int | None, int | None]) -> tuple[int, float]:
        _, antes_, depois_ = item
        piorou = (depois_ is None) or (antes_ is not None and depois_ > antes_)
        return (0 if piorou else 1, -(depois_ or 999))

    return sorted(mudancas, key=gravidade)
