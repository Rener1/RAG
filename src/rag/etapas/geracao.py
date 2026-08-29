"""
Etapa 5 — geração da resposta.

Monta o prompt aumentado (pergunta + trechos recuperados) e o entrega ao
gerador. O texto que orienta o comportamento não é escrito aqui: vem do marco
pedagógico, que é dado versionado carregado em tempo de execução e nunca prompt
no código (`docs/fase-0-desenho-e-contratos.md` §3.5).

`montar_prompt` continua existindo como o caminho sem marco — é o placeholder
genérico de antes, mantido para quando `marco.ativo` está vazio e para os testes
que provam que o montador é substituível. O caminho normal é
`montador_do_marco`.

Esta etapa depende do protocolo `MarcoPedagogico`, não do módulo que lê os
arquivos: ela não precisa saber de onde o marco veio nem como foi analisado.
"""

import re
from collections.abc import Callable

from ..modelos import TrechoRecuperado
from ..protocolos import MarcoPedagogico

# Casa "Fonte 3" em qualquer lugar, e não só um colchete inteiro: o modelo
# agrupa várias fontes num colchete só ("[Fonte 1: X, Fonte 2: Y]") com
# frequência, e exigir a forma canônica deixaria as agrupadas sem verificação.
PADRAO_CITACAO = re.compile(r"\bFonte\s+(\d+)", re.IGNORECASE)


def formatar_trechos(trechos: list[TrechoRecuperado]) -> str:
    """Trechos numerados e etiquetados pela fonte, para o modelo poder citar."""
    return "\n\n".join(
        f"[Fonte {numero}: {trecho.titulo_pagina}]\n{trecho.texto}" for numero, trecho in enumerate(trechos, start=1)
    )


def montar_prompt(pergunta: str, trechos: list[TrechoRecuperado]) -> str:
    """Prompt genérico, usado só quando nenhum marco está ativo."""
    return f"""Você responde SOMENTE com base nos trechos abaixo, que estão em inglês. \
Responda em português. Cite a fonte (o nome entre colchetes) de cada afirmação. \
Se os trechos não tiverem a resposta, diga isso claramente em vez de inventar.

TRECHOS RECUPERADOS:
{formatar_trechos(trechos)}

PERGUNTA:
{pergunta}
"""


def montar_prompt_com_marco(marco: MarcoPedagogico, pergunta: str, trechos: list[TrechoRecuperado]) -> str:
    """Prompt guiado pelo marco.

    A ordem e a escolha das seções são decisão do marco (`secoes_de_resposta`),
    não desta função: é o que permite ao comitê acrescentar uma seção sem que
    ninguém mexa em código.

    `pergunta` pode ser mais de uma linha — numa sessão dialógica ela chega como
    a demanda inicial somada ao que a pessoa respondeu na problematização.
    """
    orientacao = "\n\n".join(f"{titulo.upper()}\n{texto}" for titulo, texto in marco.secoes_de_resposta())

    return f"""{orientacao}

TRECHOS RECUPERADOS:
{formatar_trechos(trechos)}

PERGUNTA:
{pergunta}
"""


def montador_do_marco(marco: MarcoPedagogico) -> Callable[[str, list[TrechoRecuperado]], str]:
    """Fecha o marco num montador com a assinatura que `MotorRag` já aceita.

    É por aqui que o marco entra no ciclo RAG sem que o orquestrador mude uma
    linha — o encaixe já estava previsto no construtor dele.
    """

    def montar(pergunta: str, trechos: list[TrechoRecuperado]) -> str:
        return montar_prompt_com_marco(marco, pergunta, trechos)

    return montar


def validar_citacoes(texto: str, trechos: list[TrechoRecuperado]) -> list[str]:
    """Citações do texto gerado que não correspondem a nenhum trecho recuperado.

    A diretriz de explicitar fonte e autoria exige validar que o citado existe
    no contexto recuperado (`docs/fase-2-prototipo.md` §4.6) — sem isso, uma
    citação inventada é indistinguível de uma verdadeira para quem lê, que é o
    modo de falha mais caro que este sistema tem.
    """
    invalidas: list[str] = []

    for marca in PADRAO_CITACAO.finditer(texto):
        numero = int(marca.group(1))
        if not 1 <= numero <= len(trechos):
            invalidas.append(f"Fonte {numero}")

    return invalidas
