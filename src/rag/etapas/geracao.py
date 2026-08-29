"""
Etapa 5 — geração da resposta.

Recebe a pergunta e os trechos recuperados, monta o prompt aumentado e gera a
resposta. A montagem do prompt é uma função isolada de propósito: é o ponto
onde entra o marco pedagógico do projeto.

`montar_prompt` é um PLACEHOLDER. O prompt genérico que está aqui atende ao
protótipo (responder só com base nos trechos, citar a fonte, admitir quando
não sabe), mas será substituído pelo marco freiriano — problematizar antes de
responder, exigir citação por afirmação, buscar posições divergentes, recusar
entregar produto acabado. Não o "melhore" como prompt genérico: é um ponto de
extensão marcado, não uma pendência de redação.
"""

from ..modelos import TrechoRecuperado


def formatar_trechos(trechos: list[TrechoRecuperado]) -> str:
    """Trechos numerados e etiquetados pela fonte, para o modelo poder citar."""
    return "\n\n".join(
        f"[Fonte {numero}: {trecho.titulo_pagina}]\n{trecho.texto}" for numero, trecho in enumerate(trechos, start=1)
    )


def montar_prompt(pergunta: str, trechos: list[TrechoRecuperado]) -> str:
    """PLACEHOLDER — ver o cabeçalho do módulo antes de editar."""
    return f"""Você responde SOMENTE com base nos trechos abaixo, que estão em inglês. \
Responda em português. Cite a fonte (o nome entre colchetes) de cada afirmação. \
Se os trechos não tiverem a resposta, diga isso claramente em vez de inventar.

TRECHOS RECUPERADOS:
{formatar_trechos(trechos)}

PERGUNTA:
{pergunta}
"""
