"""
Pipeline RAG local do projeto IA Freiriana (Instituto Paulo Freire).

O pacote é dividido em camadas, de dentro pra fora:

- `modelos`     — estruturas de dados do domínio (Chunk, TrechoRecuperado...).
- `protocolos`  — contratos que as peças substituíveis precisam cumprir.
- `clientes`    — adaptadores dos serviços externos (Ollama, Qdrant).
- `etapas`      — as cinco etapas do pipeline, cada uma independente.
- `interface`   — menu interativo, CLI e formatação de console.

Nenhuma etapa importa outra: elas se comunicam por artefato em disco
(corpus → chunks → índice) ou por dependência injetada. Trocar o banco
vetorial ou o modelo de embedding não exige tocar nas outras etapas.
"""

__version__ = "2.0.0"
