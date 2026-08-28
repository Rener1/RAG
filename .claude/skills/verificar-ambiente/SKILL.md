---
name: verificar-ambiente
description: Verifica se o ambiente do pipeline RAG está pronto — Qdrant de pé, Ollama respondendo, modelos bge-m3 e qwen2.5:7b baixados, dependências Python importáveis, e quantos pontos há na coleção. Use antes de rodar qualquer etapa do pipeline, ou ao diagnosticar erro de conexão, coleção vazia ou resultado de busca inesperado.
---

Verifique cada item abaixo e relate o resultado como uma lista curta com ✓ / ✗. Não corrija nada
sem perguntar — o objetivo é diagnóstico.

```bash
# 1. Qdrant (esperado: HTTP 200 e a lista de coleções)
curl -s -m 3 http://localhost:6333/collections

# 2. Ollama respondendo e modelos presentes
curl -s -m 3 http://localhost:11434/api/tags | python3 -c "import sys,json; print([m['name'] for m in json.load(sys.stdin).get('models',[])])"

# 3. Dependências Python
python3 -c "import requests, qdrant_client, mwparserfromhell; print('deps ok')"

# 4. Artefatos do pipeline
ls -la data/chunks.jsonl 2>/dev/null; ls data/corpus_uesp 2>/dev/null | wc -l

# 5. Pontos indexados na coleção
curl -s -m 3 http://localhost:6333/collections/uesp_lore | python3 -c "import sys,json; d=json.load(sys.stdin)['result']; print('pontos:', d['points_count'], '| dim:', d['config']['params']['vectors']['size'])"
```

Ao relatar, interprete em vez de só despejar a saída:

- **Qdrant fora do ar** → `podman compose up -d` (não docker).
- **Modelo faltando** → `ollama pull bge-m3` e/ou `ollama pull qwen2.5:7b`.
- **`dim` diferente de 1024** → a coleção foi criada com outro modelo de embedding. Precisa ser
  apagada e recriada; `garantir_colecao()` reaproveita coleção existente em silêncio e a inserção
  falha depois com erro de dimensão.
- **`pontos: 0` ou coleção inexistente** → falta rodar `src/embedding_e_indexacao.py`.
- **`data/chunks.jsonl` ausente** → falta rodar `src/chunking.py`.
- **`data/corpus_uesp/` vazio** → falta rodar `src/baixar_corpus_uesp.py`.
