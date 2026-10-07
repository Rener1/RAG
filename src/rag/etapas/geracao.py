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

import math
import re
from collections.abc import Callable

from ..modelos import TrechoRecuperado
from ..protocolos import MarcoPedagogico

# Calibrado contra o `prompt_eval_count` que o Ollama devolve, em prompts reais
# deste pipeline (marco em português + trechos em inglês): 4,06 chars/token com
# k=3 e 4,17 com k=8. Arredondado para baixo de propósito — subestimar a razão
# superestima os tokens, e errar para o lado de sobrar janela é o lado barato.
# O Ollama não expõe `/api/tokenize` (404), então estimar é o que há.
CHARS_POR_TOKEN = 4.0

# Casa "Fonte 3" em qualquer lugar, e não só um colchete inteiro: o modelo
# agrupa várias fontes num colchete só ("[Fonte 1: X, Fonte 2: Y]") com
# frequência, e exigir a forma canônica deixaria as agrupadas sem verificação.
PADRAO_CITACAO = re.compile(r"\bFonte\s+(\d+)", re.IGNORECASE)


def estimar_tokens(texto: str) -> int:
    """Estimativa conservadora do custo em tokens de um texto."""
    return math.ceil(len(texto) / CHARS_POR_TOKEN)


def caber_no_orcamento(
    trechos: list[TrechoRecuperado],
    orcamento_em_tokens: int,
    tokens_de_overhead: int = 0,
) -> list[TrechoRecuperado]:
    """Os trechos que cabem no orçamento, descartando do fim da lista para trás.

    **Trecho inteiro ou trecho nenhum — nunca cortado no meio.** Uma fonte
    citada pela metade é pior que uma fonte ausente: quem lê não tem como saber
    que o que fundamenta a afirmação foi embora, e a citação verificável que o
    marco exige deixa de ser verificável. Sai o trecho menos relevante, inteiro.

    O primeiro trecho entra mesmo se estourar sozinho: devolver lista vazia faria
    o motor concluir que nada foi recuperado e responder "não há material", que é
    pior do que um prompt apertado. Com a janela em 8192 e o teto de chunk em
    2000 caracteres, esse caso não acontece na prática.

    `orcamento_em_tokens <= 0` desliga o corte.
    """
    if orcamento_em_tokens <= 0:
        return list(trechos)

    disponivel = orcamento_em_tokens - tokens_de_overhead
    aceitos: list[TrechoRecuperado] = []
    usados = 0

    for trecho in trechos:
        # Espelha o que `formatar_trechos` grava, mais o separador de dois \n.
        custo = estimar_tokens(f"[Fonte 00: {trecho.titulo_pagina}]\n{trecho.texto}\n\n")
        if aceitos and usados + custo > disponivel:
            break
        usados += custo
        aceitos.append(trecho)

    return aceitos


def ordenar_para_o_prompt(trechos: list[TrechoRecuperado]) -> list[TrechoRecuperado]:
    """Põe os mais relevantes nas pontas e os menos relevantes no meio.

    A atenção do modelo sobre um contexto longo tem forma de U: ele usa o começo
    e o fim e passa por cima do meio — o efeito conhecido como *lost in the
    middle*, medido a ponto de o material no meio render menos que não recuperar
    nada. Entregar em ordem decrescente, como se fazia aqui, põe o trecho menos
    relevante justamente na posição final, que é uma das duas mais atendidas.

    Intercalar resolve sem custo nenhum: o 1º abre, o 2º fecha, o 3º vem em
    segundo, e os medianos ficam no miolo, que é onde a perda dói menos.
    """
    inicio: list[TrechoRecuperado] = []
    fim: list[TrechoRecuperado] = []
    for posicao, trecho in enumerate(trechos):
        (inicio if posicao % 2 == 0 else fim).append(trecho)
    return inicio + list(reversed(fim))


def formatar_trechos(trechos: list[TrechoRecuperado]) -> str:
    """Trechos etiquetados pela fonte, para o modelo poder citar.

    **O número é a posição na relevância, não no prompt.** Os blocos saem
    intercalados por `ordenar_para_o_prompt`, mas `[Fonte 2]` continua sendo o
    segundo trecho mais relevante — que é o que a interface mostra como 2 e o que
    `validar_citacoes` confere. Numerar pela posição física faria a citação da
    resposta apontar para uma fonte diferente da que a pessoa vê na tela.
    """
    numerados = {id(trecho): numero for numero, trecho in enumerate(trechos, start=1)}
    return "\n\n".join(
        f"[Fonte {numerados[id(trecho)]}: {trecho.titulo_pagina}]\n{trecho.texto}"
        for trecho in ordenar_para_o_prompt(trechos)
    )


def formatar_conversa_anterior(historico: str) -> str:
    """Bloco da conversa anterior, ou vazio quando não há.

    Vem rotulado como contexto, não como fonte: o modelo precisa dele para
    entender "o ponto 2", mas citar a própria resposta anterior como se fosse o
    acervo seria fonte inventada com cara de verdadeira.
    """
    if not historico.strip():
        return ""
    return f"""CONVERSA ANTERIOR (só para entender a pergunta; não é fonte e não deve ser citada):
{historico}

"""


def montar_prompt(pergunta: str, trechos: list[TrechoRecuperado], historico: str = "") -> str:
    """Prompt genérico, usado só quando nenhum marco está ativo."""
    return f"""Você responde SOMENTE com base nos trechos abaixo, que estão em inglês. \
Responda em português. Cite a fonte (o nome entre colchetes) de cada afirmação. \
Se os trechos não tiverem a resposta, diga isso claramente em vez de inventar.

{formatar_conversa_anterior(historico)}TRECHOS RECUPERADOS:
{formatar_trechos(trechos)}

PERGUNTA:
{pergunta}
"""


def montar_prompt_com_marco(
    marco: MarcoPedagogico, pergunta: str, trechos: list[TrechoRecuperado], historico: str = ""
) -> str:
    """Prompt guiado pelo marco.

    A ordem e a escolha das seções são decisão do marco (`secoes_de_resposta`),
    não desta função: é o que permite ao comitê acrescentar uma seção sem que
    ninguém mexa em código.

    `pergunta` pode ser mais de uma linha — numa sessão dialógica ela chega como
    a demanda inicial somada ao que a pessoa respondeu na problematização.
    """
    orientacao = "\n\n".join(f"{titulo.upper()}\n{texto}" for titulo, texto in marco.secoes_de_resposta())

    return f"""{orientacao}

{formatar_conversa_anterior(historico)}TRECHOS RECUPERADOS:
{formatar_trechos(trechos)}

PERGUNTA:
{pergunta}
"""


def montador_do_marco(marco: MarcoPedagogico) -> Callable[[str, list[TrechoRecuperado]], str]:
    """Fecha o marco num montador com a assinatura que `MotorRag` já aceita.

    É por aqui que o marco entra no ciclo RAG sem que o orquestrador mude uma
    linha — o encaixe já estava previsto no construtor dele.
    """

    def montar(pergunta: str, trechos: list[TrechoRecuperado], historico: str = "") -> str:
        return montar_prompt_com_marco(marco, pergunta, trechos, historico)

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
