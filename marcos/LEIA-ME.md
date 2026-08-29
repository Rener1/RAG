# Como editar um marco pedagógico

Um marco é um arquivo de texto comum, nesta pasta, com extensão `.md`. Você não
precisa saber programar para editá-lo, nem instalar nada, nem pedir para
ninguém publicar: salvar o arquivo já muda o comportamento do sistema na
próxima pergunta.

O marco é um artefato pedagógico por direito próprio. Ele é versionado junto do
código, então toda alteração fica registrada, com data, autoria e a diferença
exata em relação à versão anterior — e dá para voltar atrás.

## A estrutura do arquivo

Duas partes. Primeiro o **bloco de identificação**, entre duas linhas de três
traços, com uma informação por linha:

```
---
nome: Marco pedagógico freiriano
versao: 3
autoria: Comitê pedagógico do Instituto Paulo Freire
---
```

`nome`, `versao` e `autoria` são obrigatórios. **Suba o número da versão a cada
alteração de comportamento** — é por ele que se sabe qual marco produziu qual
resposta quando duas avaliações discordam.

Depois vêm as **seções**, cada uma abrindo com dois sustenidos e um título:

```
## Papel

O texto da seção vem aqui, em prosa, quantos parágrafos você quiser.

## Instruções

E assim por diante.
```

Acento, maiúscula e espaço no título não fazem diferença: `## Formato de saída`
e `## formato de saida` são a mesma seção. O que você escrever antes do primeiro
`##` é nota para quem lê o arquivo — o sistema ignora.

## As seções que o sistema lê

| Seção | Para que serve |
|---|---|
| **Papel** | de onde o sistema fala, e o que ele é para quem pergunta |
| **Instruções** | como ele se comporta ao responder |
| **Recusas** | o que ele se recusa a fazer |
| **Formato de saída** | em que formato ele entrega |
| **Decomposição** | o que ele procura no acervo além do que foi perguntado |
| **Triagem** | como ele distingue pedido de produto acabado, dúvida factual e exploração |
| **Problematização** | que perguntas ele devolve antes de responder |

`Papel`, `Instruções` e `Formato de saída` são obrigatórias — sem elas o marco
não carrega. As outras são opcionais: sem `Problematização`, por exemplo, o
sistema simplesmente não devolve perguntas.

**Você pode criar seções novas.** Uma seção com título que não está na tabela é
acrescentada ao final das orientações de resposta, na ordem em que aparece no
arquivo. Ninguém precisa mexer em código para isso.

## Testar o que você escreveu

Do terminal, na pasta do projeto:

```
python3 main.py marcos                    # lista os marcos e aponta erro, se houver
python3 main.py --marco freiriano perguntar "sua pergunta aqui"
```

Se o arquivo tiver algum problema — bloco de identificação sem fechar, seção
obrigatória faltando, seção vazia — o sistema diz qual é o problema, em que
arquivo, e o que fazer. Ele **não** volta a se comportar como um chatbot comum
em silêncio: sem marco válido, ele não responde.

## Trocar o marco em uso

O padrão é o `generico`, que serve só para testar o mecanismo sobre o corpus
descartável. Para mudar de forma permanente, escreva em `config.toml`:

```toml
[marco]
ativo = "freiriano"
```

Ou, sem editar arquivo nenhum: `python3 main.py config` → opção Configuração no
menu → seção `marco` → campo `ativo` → depois `salvar`.
