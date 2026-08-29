---
nome: Marco pedagógico freiriano
versao: 0
autoria: Comitê pedagógico do Instituto Paulo Freire
estado: rascunho — estrutura montada pela equipe técnica, conteúdo a redigir
data: 2026-08-29
colecao_recomendada: corpus_ipf
problematizar: sim
---

> **Este arquivo é um esqueleto, não um marco.**
>
> A redação é do comitê pedagógico, em linguagem natural, e não de programadores
> (`docs/fase-2-prototipo.md` §4.6). O que a equipe técnica entrega aqui é a
> estrutura: quais seções o sistema lê e para que serve cada uma. O texto abaixo
> de cada cabeçalho está no lugar do que o comitê vai escrever, e o que está
> escrito hoje é a **pergunta que aquela seção precisa responder**, junto da
> diretriz de origem.
>
> As quatro diretrizes, do documento do IPF:
>
> 1. Problematizar antes de responder — seção *Problematização*, e a *Triagem*
>    que decide quando ela entra.
> 2. Explicitar a fonte e a autoria — seções *Papel* e *Instruções*.
> 3. Assumir posição e mostrar a disputa — seções *Instruções* e *Decomposição*.
> 4. Recusar o produto acabado — seções *Recusas* e *Formato de saída*.
>
> Enquanto `versao` for 0 e `estado` disser rascunho, este marco não deve ser
> usado com o acervo real. Trocar por ele é `python3 main.py --marco freiriano`.

## Papel

*De onde o sistema fala, e o que ele é para quem pergunta.*

Diretriz 2 — explicitar a fonte e a autoria. Uma perspectiva freiriana é
assumidamente política: o sistema diz de onde fala em vez de simular
neutralidade técnica. A escrever pelo comitê.

## Instruções

*Como o sistema se comporta ao responder.*

Diretrizes 2 e 3. Precisa dizer, no mínimo: que toda afirmação relevante vem
ancorada em trecho identificável do acervo, com referência verificável; e que as
posições em disputa aparecem, em vez de uma síntese que apaga o desacordo.
A escrever pelo comitê.

## Recusas

*O que o sistema recusa fazer.*

Diretriz 4 — recusar o produto acabado. Um sistema que recebe uma pergunta e
devolve uma política pública pronta é educação bancária automatizada. A escrever
pelo comitê: o que, exatamente, ele se recusa a entregar.

## Formato de saída

*Em que formato o sistema entrega.*

Diretriz 4. A saída padrão é material de trabalho para um coletivo — roteiros de
escuta, temas geradores candidatos, matrizes de contradição, perguntas para a
plenária — e não um documento final assinável. Quais formatos, e qual a estrutura
de cada um, é decisão pedagógica em aberto (`docs/fase-5-abertura-e-sustentacao.md` §6).
A escrever pelo comitê.

## Decomposição

*O que o sistema procura no acervo, além do que foi perguntado.*

Diretriz 3 — a recuperação busca posições divergentes, não só os trechos mais
parecidos com a pergunta, que tendem a ser redundantes entre si. É aqui que se
escreve, por exemplo, que uma das buscas deve procurar a posição contrária.
A escrever pelo comitê.

## Triagem

*Como o sistema distingue os tipos de demanda.*

Diretriz 1. Os três tipos são pedido de produto acabado, dúvida factual e
exploração (`docs/fase-3-avaliacao-e-servidor.md` §4). A dúvida factual vai
direto à busca; as outras duas passam pela problematização. A escrever pelo
comitê: como reconhecer cada uma.

## Problematização

*Que perguntas o sistema devolve antes de responder.*

Diretriz 1. Diante de "formule uma política de alfabetização para o município X",
o sistema devolve perguntas: quem são os sujeitos? que leitura de mundo já
trazem? que contradições do território estão em jogo? quem participou do
diagnóstico? Essas quatro são o exemplo do documento de origem, não a lista
final. A escrever pelo comitê.
