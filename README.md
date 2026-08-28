# IA Freiriana — protótipo de RAG local (Fase 2)

Pipeline RAG rodando inteiramente na máquina local: download de corpus → chunking →
embedding/indexação → recuperação → geração. Protótipo da **Fase 2** do projeto IA Freiriana
(Instituto Paulo Freire). O plano completo por fases está em [docs/](docs/).

O corpus atual (lore de Elder Scrolls, da UESP) é **descartável** — serve só para exercitar o
pipeline com volume real enquanto o acervo do Centro de Referência Paulo Freire não fica pronto.

## Estrutura

```
src/     código do pipeline — um arquivo por etapa, executável direto
data/    artefatos gerados (corpus, chunks, storage do Qdrant) — não versionado
docs/    plano por fases
```

## Pré-requisitos

```bash
pip3 install -r requirements.txt
podman compose up -d      # Qdrant em localhost:6333 (painel: /dashboard)
ollama pull bge-m3        # embedding, 1024 dimensões
ollama pull qwen2.5:7b    # geração
```

Use **podman**, não docker — o arquivo se chama `docker-compose.yml` por convenção de nome
apenas, e o volume usa a flag `:Z` do SELinux.

## Rodando o pipeline

A ordem importa: cada etapa consome a saída da anterior. Rode a partir da raiz do repositório.

```bash
python3 src/baixar_corpus_uesp.py    # rede → data/corpus_uesp/*.txt   (~9k páginas, demorado)
python3 src/chunking.py              # data/corpus_uesp/ → data/chunks.jsonl
python3 src/embedding_e_indexacao.py # data/chunks.jsonl → Qdrant (coleção uesp_lore)
python3 src/busca_teste.py           # só recuperação, sem LLM de geração
python3 src/orquestrador.py          # ciclo RAG completo
```

`src/busca_teste.py` isola a camada de recuperação de propósito — ao depurar qualidade de
resposta, confira a recuperação com ele antes de mexer no prompt de geração.

## Configuração

Os parâmetros (modelo, coleção, `k`, tamanhos de chunk, paralelismo) ficam como **constantes no
topo de cada arquivo**, por decisão de projeto — não há `.env` nem argumentos de linha de comando.
Para mudar algo, edite a constante.
