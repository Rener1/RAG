# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## O que é este repositório

Protótipo da **Fase 2** do projeto IA Freiriana (Instituto Paulo Freire): um pipeline RAG local
completo — download de corpus → chunking → embedding/indexação → recuperação → geração.

O plano por fases está em `docs/`. Leia sob demanda, não preventivamente:
`@docs/00-plano-geral-implementacao.md`

**O corpus UESP é descartável.** `data/corpus_uesp/` (lore de Elder Scrolls) existe só para exercitar o
pipeline com volume real enquanto o acervo do Centro de Referência Paulo Freire não está pronto
(Fase 1). Ao trocar para o corpus real, muda a coleção (`uesp_lore` → `corpus_ipf`) e a fonte de
download — não a arquitetura. Não trate a lore como domínio do projeto.

## Idioma do código

**Todo o código é escrito em português brasileiro** — nomes de função, variáveis, campos de
dataclass, docstrings, comentários e saída de `print`. Isso é deliberado e 100% consistente.
Ao escrever ou editar código aqui, mantenha pt-BR (`buscar`, `montar_prompt`, `NOME_COLECAO`,
`titulo_pagina`), nunca inglês.

As mensagens ao usuário nesta conversa também em português.

## Pipeline — a ordem importa

Cada etapa consome a saída da anterior. Rodar fora de ordem produz resultado vazio ou desatualizado:

```
python3 src/baixar_corpus_uesp.py    # rede → data/corpus_uesp/*.txt   (~9k páginas, demorado)
python3 src/chunking.py              # data/corpus_uesp/ → data/chunks.jsonl
python3 src/embedding_e_indexacao.py # data/chunks.jsonl → Qdrant (coleção uesp_lore)
python3 src/busca_teste.py           # só recuperação, sem LLM de geração
python3 src/orquestrador.py          # ciclo RAG completo
```

Rode sempre a partir da raiz do repositório. Os scripts resolvem `data/` a partir de
`RAIZ_PROJETO` (`Path(__file__).resolve().parents[1]`), então o diretório atual não quebra
nada — mas os comandos documentados assumem a raiz.

`src/busca_teste.py` isola a camada de recuperação de propósito: recall@k é avaliável sem gerar texto.
Ao depurar qualidade de resposta, verifique a recuperação com ele antes de mexer no prompt.

## Serviços — precisam estar de pé

```
podman compose up -d      # Qdrant em localhost:6333 (painel: /dashboard)
ollama pull bge-m3        # embedding, 1024 dimensões
ollama pull qwen2.5:7b    # geração
```

Use **podman**, não docker — o arquivo se chama `docker-compose.yml` por convenção de nome apenas,
e o volume usa a flag `:Z` do SELinux.

## Armadilhas

- **`DIMENSAO_VETOR = 1024` tem que bater com a saída do `bge-m3`.** Trocar o modelo de embedding
  exige apagar e recriar a coleção — `garantir_colecao()` reaproveita a coleção existente em
  silêncio e a inserção falha depois, com erro de dimensão.
- **Reindexar é idempotente.** IDs vêm de `uuid5` sobre o `chunk_id`, então rodar
  `embedding_e_indexacao.py` de novo sobrescreve em vez de duplicar.
- **Os parâmetros de configuração ficam como constantes no topo de cada arquivo**, não em `.env`
  nem em CLI. Para mudar modelo, coleção ou `k`, edite as constantes.
- **`montar_prompt()` em `src/orquestrador.py` é um placeholder.** O prompt genérico ali será
  substituído pelo marco pedagógico (problematizar antes de responder, exigir citação por
  afirmação, buscar posições divergentes, recusar produto acabado). Não o "melhore" como prompt
  genérico — é um ponto de extensão marcado.
- **`buscar()` tem um `NOTE` marcando onde entra o intermediador de decomposição de consulta.**
  Ainda não implementado, por decisão.

## Arquivos que você NÃO deve ler ou varrer em massa

São artefatos gerados, não fonte. Consulte-os por amostragem (`head`, `ls | wc -l`), nunca
inteiros nem com grep recursivo:

- `data/corpus_uesp/` — 8896 arquivos `.txt`
- `data/chunks.jsonl` — ~50 MB
- `data/qdrant_storage/` — dados binários do Qdrant

## Estrutura

```
src/            código do pipeline — um arquivo por etapa, executável direto
data/           artefatos gerados (corpus, chunks, storage do Qdrant) — todo o conteúdo é gitignored
docs/           plano por fases + PDF de origem do IPF
.claude/        skills do projeto (pipeline, verificar-ambiente)
```

Não há pacote instalável nem `__init__.py`: cada etapa é um script independente, sem import
entre elas. `docker-compose.yml`, `requirements.txt` e `ruff.toml` ficam na raiz, onde as
ferramentas os procuram.

## Dependências

`pip3 install -r requirements.txt`. Instalação global, sem virtualenv (Python 3.14).
