---
name: verificar-ambiente
description: Verifica se o ambiente do pipeline RAG está pronto — Qdrant de pé, Ollama respondendo, modelos bge-m3 e qwen2.5:7b baixados, dependências Python importáveis, e quantos pontos há na coleção. Use antes de rodar qualquer etapa do pipeline, ou ao diagnosticar erro de conexão, coleção vazia ou resultado de busca inesperado.
---

O projeto já traz esse diagnóstico pronto. Rode, a partir da raiz do repositório:

```bash
python3 main.py ambiente
```

Ele verifica, em uma passada, e já imprime a sugestão de conserto de cada item que falhar:

- dependências Python importáveis;
- Ollama respondendo, e os modelos de embedding e geração baixados (compara ignorando a etiqueta
  `:latest`, então `bge-m3` e `bge-m3:latest` contam como o mesmo);
- Qdrant respondendo, e a coleção configurada — existência, número de pontos e **dimensão do
  vetor**, comparada com a que o modelo de embedding atual produz;
- corpus baixado e `data/chunks.jsonl` presente.

Código de saída: 0 quando dá para perguntar, 1 quando há falha.

Para diagnosticar outra coleção: `python3 main.py ambiente --colecao NOME`.

## Ao relatar

Repasse a lista com ✓ / ✗ e **interprete** — não despeje a saída crua. O comando já sugere o
conserto de cada item; o que se espera de você é dizer qual etapa do pipeline está faltando e o
que fazer em seguida. **Não corrija nada sem perguntar**: o objetivo é diagnóstico.

Os consertos mais comuns:

- **Qdrant fora do ar** → `podman compose up -d` (não docker).
- **Modelo faltando** → `ollama pull bge-m3` e/ou `ollama pull qwen2.5:7b`.
- **Dimensão diferente da esperada** → a coleção foi criada com outro modelo de embedding.
  `python3 main.py indexar --recriar` apaga e refaz — leva horas, então confirme antes.
- **`pontos: 0` ou coleção inexistente** → falta rodar `python3 main.py indexar`.
- **`data/chunks.jsonl` ausente** → falta rodar `python3 main.py chunking`.
- **`data/corpus_uesp/` vazio** → falta rodar `python3 main.py baixar`.

## Se o comando não rodar

Aí o problema é anterior ao pipeline (Python, dependências, caminho errado). Confira na mão:

```bash
python3 -c "import requests, qdrant_client, mwparserfromhell; print('deps ok')"
curl -s -m 3 http://localhost:6333/collections
curl -s -m 3 http://localhost:11434/api/tags
```
