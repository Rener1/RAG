# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## O que é este repositório

Protótipo da **Fase 2** do projeto IA Freiriana (Instituto Paulo Freire): um pipeline RAG local
completo — download de corpus → chunking → embedding/indexação → recuperação → geração.

O plano por fases está em `docs/`. Leia sob demanda, não preventivamente:
`@docs/00-plano-geral-implementacao.md`

**O corpus UESP é descartável.** `data/corpus_uesp/` (lore de Elder Scrolls) existe só para
exercitar o pipeline com volume real enquanto o acervo do Centro de Referência Paulo Freire não
está pronto (Fase 1). Ao trocar para o corpus real, muda a coleção (`uesp_lore` → `corpus_ipf`) e
o módulo de download — não a arquitetura. Não trate a lore como domínio do projeto.

## Idioma do código

**Todo o código é escrito em português brasileiro** — nomes de função, variáveis, campos de
dataclass, docstrings, comentários e saída de `print`. Isso é deliberado e 100% consistente.
Ao escrever ou editar código aqui, mantenha pt-BR (`buscar`, `montar_prompt`, `NOME_COLECAO`,
`titulo_pagina`), nunca inglês.

As mensagens ao usuário nesta conversa também em português.

## Ponto de entrada único

Tudo passa por `main.py` — menu interativo sem argumento, subcomandos para automação. As duas
formas chamam as mesmas funções em `src/rag/interface/acoes.py`, então **não existe
funcionalidade que só o menu ou só a CLI alcance**. Ao adicionar uma capacidade, adicione a ação
lá e ligue nas duas portas.

```bash
python3 main.py                    # menu
python3 main.py ambiente           # diagnóstico (use antes de investigar qualquer falha)
python3 main.py chunking
python3 main.py indexar            # retoma de onde parou; --recriar para refazer
python3 main.py buscar "..."       # só recuperação
python3 main.py perguntar "..."    # ciclo RAG completo
```

Rode a partir da raiz do repositório. Os caminhos são resolvidos a partir de
`config.RAIZ_PROJETO`, então o diretório atual não quebra nada, mas os comandos documentados
assumem a raiz.

## Arquitetura — o que não pode ser quebrado

```
main.py              fino: só ajusta sys.path e delega
src/rag/
  config.py          parâmetros de todas as etapas
  protocolos.py      contratos (Embutidor, Gerador, RepositorioVetorial, ColetorDeCorpus...)
  orquestrador.py    MotorRag — o ciclo recuperação + geração
  servico.py         onde as implementações concretas encontram os protocolos
  clientes/          Ollama, Qdrant, UESP, sessão HTTP com repetição
  etapas/            download, chunking, indexacao, recuperacao, geracao
  interface/         console, menu, cli, acoes
```

Duas regras estruturais, ambas verificáveis:

1. **Nenhum módulo em `etapas/` importa outro módulo de `etapas/`.** Elas se comunicam por
   artefato em disco. É o que permite refazer uma etapa sem afetar as outras.
2. **As etapas dependem de `protocolos.py`, não de `clientes/`.** Trocar o banco vetorial é
   escrever outra classe com os mesmos métodos e mudar uma linha em `servico.py`. Os testes
   dependem disso: rodam com dublês, sem Qdrant nem Ollama.

Verificáveis com `grep -rn "clientes" src/rag/etapas/` (deve vir vazio) e conferindo que nenhum
import em `etapas/` aponta para outro módulo de `etapas/`. Se precisar quebrar uma delas, é sinal
de que o código pertence a `orquestrador.py` ou a `clientes/`, não à etapa.

## Pipeline — a ordem importa

Cada etapa consome a saída da anterior:

```
download    → data/corpus_uesp/*.txt   (~9k páginas, demorado)
chunking    → data/chunks.jsonl
indexacao   → coleção uesp_lore no Qdrant   (horas)
recuperacao → trechos
geracao     → resposta
```

`buscar` isola a camada de recuperação de propósito: recall@k é avaliável sem gerar texto.
Ao depurar qualidade de resposta, verifique a recuperação com ele antes de mexer no prompt.

## Serviços — precisam estar de pé

```
podman compose up -d      # Qdrant em localhost:6333 (painel: /dashboard)
ollama pull bge-m3        # embedding, 1024 dimensões
ollama pull qwen2.5:7b    # geração
```

Use **podman**, não docker — o arquivo se chama `docker-compose.yml` por convenção de nome apenas,
e o volume usa a flag `:Z` do SELinux.

`python3 main.py ambiente` diagnostica os dois serviços, os modelos, a dimensão da coleção e os
artefatos de cada etapa. É o primeiro comando a rodar diante de qualquer erro.

## Armadilhas

- **`montar_prompt()` em `etapas/geracao.py` é um placeholder.** O prompt genérico ali será
  substituído pelo marco pedagógico (problematizar antes de responder, exigir citação por
  afirmação, buscar posições divergentes, recusar produto acabado). Não o "melhore" como prompt
  genérico — é um ponto de extensão marcado. `MotorRag` aceita outro montador por injeção.
- **`Recuperador.buscar()` tem um `NOTE`** marcando onde entra o intermediador de decomposição de
  consulta. Ainda não implementado, por decisão.
- **Mudar a estratégia de chunking invalida o índice inteiro.** A saída de `chunking` com a
  estratégia padrão (`paragrafo`) é byte a byte igual à do protótipo original — 69285 chunks,
  sha256 `a991de28...`. `paragrafo_agrupado` existe e é melhor (não descarta parágrafo curto),
  mas trocar exige reindexar tudo, o que leva horas. Não troque de passagem.
- **`DIMENSAO_VETOR` tem que bater com a saída do modelo de embedding.** Isso agora é
  *verificado antes* de qualquer processamento (`garantir_colecao`), com erro explicado — não é
  mais o modo de falha silencioso que era. Ao trocar o modelo, use `indexar --recriar`.
- **A indexação retoma por padrão.** Chunks já indexados são pulados (consulta por `uuid5` do
  `chunk_id`), então repetir a etapa custa segundos em vez de horas. `--sem-retomada` desliga.
- **Os parâmetros ficam em `src/rag/config.py`**, não espalhados pelos módulos e não em `.env`.
  O menu (opção 7) e as flags da CLI ajustam em memória, só para aquela execução.

## Testes

```bash
python3 -m unittest discover -s tests -t tests
```

45 testes, sem dependência de serviço externo ou rede. Ao mexer em chunking, indexação ou no ciclo
RAG, rode antes e depois — é o que protege a compatibilidade do índice existente.

## Arquivos que você NÃO deve ler ou varrer em massa

São artefatos gerados, não fonte. Consulte-os por amostragem (`head`, `ls | wc -l`), nunca
inteiros nem com grep recursivo:

- `data/corpus_uesp/` — 8896 arquivos `.txt`
- `data/chunks.jsonl` — ~50 MB
- `data/qdrant_storage/` — dados binários do Qdrant

## Dependências

`pip3 install -r requirements.txt`. Instalação global, sem virtualenv (Python 3.14). O projeto não
é empacotado: `main.py` põe `src/` no `sys.path` e roda direto do clone.
