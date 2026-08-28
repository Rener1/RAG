---
name: pipeline
description: Roda o pipeline RAG completo na ordem correta, com checagem de pré-requisitos entre as etapas. Aceita o nome de uma etapa para rodar só a partir dela.
disable-model-invocation: true
---

Argumento recebido: `$ARGUMENTS`

Se vier vazio, rode a partir da primeira etapa que ainda não tem saída. Se vier o nome de uma etapa
(`baixar`, `chunking`, `embedding`, `busca`, `orquestrador`), rode a partir dela.

## Antes de começar

Invoque a skill `verificar-ambiente` e resolva o que estiver faltando. Não siga com Qdrant fora do
ar ou modelo não baixado — as etapas falham no meio e deixam estado parcial.

## Etapas, em ordem

Cada uma consome a saída da anterior. Rode uma de cada vez, **a partir da raiz do
repositório**, e confira a saída antes de seguir.

| # | Comando | Produz | Custo |
|---|---------|--------|-------|
| 1 | `python3 src/baixar_corpus_uesp.py` | `data/corpus_uesp/*.txt` | rede, ~9k páginas, **demorado** |
| 2 | `python3 src/chunking.py` | `data/chunks.jsonl` (~50 MB) | minutos |
| 3 | `python3 src/embedding_e_indexacao.py` | coleção `uesp_lore` no Qdrant | **muito demorado** — GPU/CPU local |
| 4 | `python3 src/busca_teste.py` | relatório de recuperação | segundos |
| 5 | `python3 src/orquestrador.py` | respostas geradas | ~1 min por pergunta |

**Confirme com o usuário antes das etapas 1 e 3.** A 1 faz milhares de requisições à UESP; a 3 pode
levar horas. Se a saída da etapa já existir (`data/corpus_uesp/` populado, `data/chunks.jsonl` presente,
coleção com pontos), diga isso e pergunte se é para refazer em vez de rodar por padrão.

Rode as etapas 1 e 3 em background (`run_in_background`) e acompanhe o progresso — ambas imprimem
contagem parcial de lotes.

## Ao terminar

Relate: quantas páginas baixadas, quantos chunks gerados, quantos pontos indexados, e o resultado
de `src/busca_teste.py`. Se os scores de recuperação vierem baixos (< 0.5 no topo), diga isso — é sinal
de problema na recuperação, e o lugar de investigar é o chunking, não o prompt de geração.

## Se algo falhar

- Lote isolado falhando nas etapas 1 ou 3: os scripts capturam a exceção e seguem. Rodar de novo é
  seguro — a 1 pula arquivo já existente, a 3 sobrescreve por `uuid5` em vez de duplicar.
- Erro de dimensão de vetor na etapa 3: a coleção existe com outra dimensão. Ver `verificar-ambiente`.
