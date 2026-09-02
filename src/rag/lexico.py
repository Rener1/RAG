"""
Recuperação léxica (BM25) e a fusão dela com a busca densa.

A busca vetorial acerta o sentido e erra o termo exato: quem pergunta por "tema
gerador" quer o documento que contém *aquela expressão*, e o embedding tende a
diluí-la em "assunto", "tópico", "questão geradora". O BM25 faz o oposto —
premia termo exato e raro, e não entende sinônimo nenhum. Os dois erram em
direções opostas, e é isso que faz a fusão render.

**Desligado por padrão, e a razão é de calendário, não de mérito.** Medido nos 40
casos do gabarito:

    pergunta em português, acervo em inglês:   denso 85%  ·  híbrido 82%
    pergunta e acervo no mesmo idioma:         denso 90%  ·  híbrido 92%

Recuperação léxica depende de o termo coexistir dos dois lados, e entre idiomas
diferentes quase só nome próprio sobrevive — BM25 sozinho faz 50% no corpus atual
contra 65% quando a consulta está em inglês. O acervo do IPF será de idioma
casado, com vocabulário técnico exato ("conscientização", "práxis", "tema
gerador"), que é o cenário favorável. Está pronto para quando ele chegar.

Mora na raiz do pacote, e não em `etapas/`, pelo mesmo motivo de
`orquestrador.py` e `mediacao.py`: compõe dois recuperadores, e isso não pertence
a nenhuma etapa.
"""

import json
import math
import re
from dataclasses import replace
from functools import cached_property
from pathlib import Path

from .config import ConfigBusca
from .erros import ErroPreRequisito
from .mediacao import fundir_por_rrf
from .modelos import TrechoRecuperado
from .protocolos import RecuperadorDeTrechos

# Sequências alfanuméricas, com os acentos do português. Sem radicalização
# (stemming): ela é específica de idioma, e o acervo do IPF ainda não existe para
# se saber o que compensa. Termo exato já é o que o BM25 explora melhor.
PADRAO_DE_TOKEN = re.compile(r"[0-9a-zà-ÿ]+", re.IGNORECASE)

TAMANHO_MINIMO_DE_TOKEN = 2

# Constantes clássicas do BM25. `K1` controla a saturação da frequência do termo,
# `B` o quanto o tamanho do documento penaliza. Não foram ajustadas: o ganho de
# ajustá-las é pequeno perto do de ter o corpus certo.
K1 = 1.5
B = 0.75


def tokenizar(texto: str) -> list[str]:
    return [t for t in PADRAO_DE_TOKEN.findall(texto.lower()) if len(t) >= TAMANHO_MINIMO_DE_TOKEN]


class IndiceLexico:
    """Índice invertido BM25 sobre o `chunks.jsonl`.

    Construído sob demanda e mantido em memória pelo processo. Não persiste em
    disco de propósito: construir custa ~2 s para 69285 chunks, e uma cópia em
    disco traria invalidação para manter — mais peça para desalinhar do que o
    tempo que economizaria. Se o acervo crescer a ponto de isso incomodar, a
    medida a refazer é esta, não a decisão.
    """

    def __init__(self, caminho_dos_chunks: Path) -> None:
        self._caminho = caminho_dos_chunks

    @cached_property
    def _indice(self) -> tuple[dict[str, list[tuple[int, int]]], list[int], list[dict], float]:
        if not self._caminho.exists():
            raise ErroPreRequisito(
                f"Busca léxica pedida, mas {self._caminho.name} não existe.",
                sugestao="Rode `python3 main.py chunking` antes, ou desligue com `--sem-hibrido`.",
            )

        postings: dict[str, list[tuple[int, int]]] = {}
        tamanhos: list[int] = []
        documentos: list[dict] = []

        with self._caminho.open(encoding="utf-8") as arquivo:
            for numero, linha in enumerate(arquivo):
                dados = json.loads(linha)
                tokens = tokenizar(dados["texto"])
                tamanhos.append(len(tokens))
                documentos.append(dados)

                frequencias: dict[str, int] = {}
                for token in tokens:
                    frequencias[token] = frequencias.get(token, 0) + 1
                for token, frequencia in frequencias.items():
                    postings.setdefault(token, []).append((numero, frequencia))

        media = sum(tamanhos) / len(tamanhos) if tamanhos else 0.0
        return postings, tamanhos, documentos, media

    @property
    def total_de_documentos(self) -> int:
        return len(self._indice[2])

    def buscar(self, pergunta: str, k: int | None = None) -> list[TrechoRecuperado]:
        """Trechos mais bem pontuados por BM25, do maior para o menor."""
        postings, tamanhos, documentos, media = self._indice
        total = len(documentos)
        if not total:
            return []

        notas: dict[int, float] = {}
        for token in set(tokenizar(pergunta)):
            lista = postings.get(token)
            if not lista:
                continue
            # IDF: termo que aparece em quase todo documento não distingue nada,
            # e é o que faz palavra comum não dominar a soma.
            idf = math.log(1 + (total - len(lista) + 0.5) / (len(lista) + 0.5))
            for documento, frequencia in lista:
                normalizado = 1 - B + B * tamanhos[documento] / media if media else 1.0
                notas[documento] = notas.get(documento, 0.0) + idf * frequencia * (K1 + 1) / (
                    frequencia + K1 * normalizado
                )

        # Empate desfeito pelo índice do documento, para a ordem não variar entre
        # execuções e a avaliação continuar comparável.
        melhores = sorted(notas, key=lambda d: (-notas[d], d))[: k or 10]
        return [
            TrechoRecuperado(
                texto=documentos[d]["texto"],
                titulo_pagina=documentos[d]["titulo_pagina"],
                documento_origem=documentos[d]["documento_origem"],
                chunk_id=documentos[d]["chunk_id"],
                score=notas[d],
            )
            for d in melhores
        ]


def reescalar_para(
    lexicos: list[TrechoRecuperado],
    densos: list[TrechoRecuperado],
) -> list[TrechoRecuperado]:
    """Põe os scores léxicos na escala dos densos, preservando a ordem.

    **Não é cosmético.** Cosseno vive perto de 0,6 e BM25 chega a 10 ou mais, e
    `fundir_por_rrf` conserva o melhor score original de cada trecho — então um
    chunk achado só pelo léxico entraria no resultado com um número fora de
    escala. Quem depende disso é a política de quantidade dinâmica, que corta por
    fração do score do primeiro colocado: um valor dez vezes maior no topo faz o
    corte descartar quase tudo. Medido, `trechos/caso` caía de 8,9 para 6,5.

    O mapeamento é linear sobre a faixa observada dos densos. Não pretende dar
    sentido de similaridade aos números — pretende que a ordem seja utilizável
    pelas camadas seguintes sem que elas precisem saber da fusão.
    """
    if not lexicos:
        return []
    if not densos:
        return list(lexicos)

    teto = max(t.score for t in densos)
    piso = min(t.score for t in densos)
    maior = max(t.score for t in lexicos)
    menor = min(t.score for t in lexicos)
    intervalo = maior - menor

    def convertido(trecho: TrechoRecuperado) -> TrechoRecuperado:
        fracao = (trecho.score - menor) / intervalo if intervalo else 1.0
        return replace(trecho, score=piso + fracao * (teto - piso))

    return [convertido(t) for t in lexicos]


class RecuperadorHibrido:
    """Funde o ranking denso com o léxico. Cumpre `RecuperadorDeTrechos`.

    **O denso pesa mais, e isso é medido.** Com pesos iguais o híbrido fica
    abaixo do denso sozinho (88% contra 90%); com o denso pesando 2 ou mais, sobe
    para 92%. Pesos 2, 3, 5 e 10 dão o mesmo resultado — o léxico não dirige o
    ranking, ele complementa: o denso ordena e o esparso promove o que o denso
    deixou passar. Dar voto igual ao complemento é o que estraga.
    """

    def __init__(
        self,
        denso: RecuperadorDeTrechos,
        lexico: IndiceLexico,
        config: ConfigBusca,
    ) -> None:
        self._denso = denso
        self._lexico = lexico
        self._config = config

    def buscar(self, pergunta: str, k: int | None = None) -> list[TrechoRecuperado]:
        alvo = k or self._config.k
        candidatos = max(alvo, self._config.k_maximo)

        denso = self._denso.buscar(pergunta, k=candidatos)
        try:
            lexico = self._lexico.buscar(pergunta, k=candidatos)
        except ErroPreRequisito:
            # Sem o `chunks.jsonl` a busca densa continua servindo sozinha. A
            # recuperação não pode parar por causa de uma camada opcional.
            return denso[:alvo]

        rankings: list[list[TrechoRecuperado]] = []
        # Repetir o ranking denso é como se dá peso a ele no RRF sem mudar a
        # função de fusão, que já é usada pela mediação e está testada.
        rankings.extend([list(denso)] * max(1, self._config.peso_denso))
        rankings.append(reescalar_para(lexico, denso))

        return fundir_por_rrf(rankings)[:alvo]
