---
name: pipeline
description: Roda o pipeline RAG completo na ordem correta, com checagem de pré-requisitos entre as etapas. Aceita o nome de uma etapa para rodar só a partir dela.
disable-model-invocation: true
---

Argumento recebido: `$ARGUMENTS`

Se vier vazio, rode a partir da primeira etapa que ainda não tem saída. Se vier o nome de uma etapa
(`baixar`, `chunking`, `indexar`, `buscar`, `perguntar`), rode a partir dela.

Tudo passa por `main.py`, a partir da raiz do repositório.

## Antes de começar

```bash
python3 main.py ambiente
```

Diagnostica serviços, modelos, dimensão da coleção e artefatos de cada etapa, e sugere o conserto
de cada item que falhar. Código de saída 1 quando há falha. Não siga com Qdrant fora do ar ou
modelo não baixado — as etapas falham no meio e deixam estado parcial.

## Etapas, em ordem

Cada uma consome a saída da anterior. Rode uma de cada vez e confira a saída antes de seguir.

| # | Comando | Produz | Custo |
|---|---------|--------|-------|
| 1 | `python3 main.py baixar` | `data/corpus_uesp/*.txt` | rede, ~9k páginas, **demorado** |
| 2 | `python3 main.py chunking` | `data/chunks.jsonl` (~50 MB) | segundos |
| 3 | `python3 main.py indexar` | coleção `uesp_lore` no Qdrant | **muito demorado** — GPU/CPU local |
| 4 | `python3 main.py buscar "pergunta"` | trechos recuperados | segundos |
| 5 | `python3 main.py perguntar "pergunta"` | resposta gerada | ~1 min por pergunta |

**Confirme com o usuário antes das etapas 1 e 3.** A 1 faz milhares de requisições à UESP; a 3
pode levar horas. Quando chamados sem terminal interativo, esses comandos não pedem confirmação —
então a confirmação tem que vir de você, antes.

Rode as etapas 1 e 3 em background (`run_in_background`) e acompanhe: ambas mostram progresso.

## O que já mudou de comportamento

- **Indexar retoma por padrão.** Chunks já indexados são pulados, então repetir a etapa 3 num
  índice completo custa segundos, não horas. Use `--recriar` para refazer do zero (necessário ao
  trocar o modelo de embedding), `--sem-retomada` para reprocessar sem apagar.
- **Chunking sobrescreve `data/chunks.jsonl`.** Com a estratégia padrão a saída é idêntica à
  anterior; com `--estrategia paragrafo_agrupado` muda, e aí o índice inteiro fica defasado.
- **Dimensão incompatível é detectada antes de processar**, com mensagem explicando o conserto.

## Ao terminar

Relate: quantas páginas baixadas, quantos chunks gerados, quantos pontos indexados, e o resultado
da busca. Se os scores de recuperação vierem baixos (< 0.5 no topo), diga isso — é sinal de
problema na recuperação, e o lugar de investigar é o chunking, não o prompt de geração.

## Se algo falhar

- Lote isolado falhando nas etapas 1 ou 3: os comandos capturam a exceção, seguem, e relatam
  quantos lotes falharam no fim. Repetir é seguro — a 1 pula arquivo já existente, a 3 retoma.
- Qualquer erro conhecido sai com mensagem e sugestão de conserto, sem traceback. Se aparecer
  traceback, é bug — vale investigar, não contornar.
