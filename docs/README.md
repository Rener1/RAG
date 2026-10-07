# Documentação — por onde começar

Cada documento tem uma função, e cada fato mora em um documento só; os outros apontam para ele
([diretrizes](diretrizes.md) §3). Todos abrem com uma linha de navegação de volta para cá.

## Por onde começar, conforme o que você procura

| Você quer… | Leia |
|---|---|
| entender o projeto em uma página | [Plano geral](plano/00-plano-geral-implementacao.md) §1 |
| saber o que está pronto, o que falta e o que vem a seguir | [Roadmap](roadmap.md) |
| saber as regras para mexer no código ou nos documentos | [Diretrizes](diretrizes.md) |
| entender como o código é organizado | [Arquitetura](engenharia/arquitetura.md) |
| saber por que um parâmetro vale o que vale | [Medições](engenharia/medicoes.md) |
| instalar e rodar | [README do repositório](../README.md) |
| editar um marco pedagógico (sem programar) | [Como editar um marco](../marcos/LEIA-ME.md) |

## Na raiz de `docs/` — o que vale para todo o resto

| Documento | Função | Atualiza quando |
|---|---|---|
| [Roadmap](roadmap.md) | **O que fazer.** Onde o software está, o que falta em cada fase, em que ordem, e o que espera decisão | um item começa, termina ou é descartado; um padrão muda |
| [Diretrizes](diretrizes.md) | **Como fazer.** As regras de modularidade, código, documentação e medição | a equipe decide uma regra nova |

## `plano/` — o que o Instituto quer

O plano por fases, com portões, papéis e orçamento. Vem do documento de origem do Instituto Paulo
Freire, é institucional e **não se edita para acompanhar o código**: quando os dois divergem, o
plano diz o que se quer e o [roadmap](roadmap.md) diz o que se tem.

| Documento | Do que trata |
|---|---|
| [00 — Plano geral](plano/00-plano-geral-implementacao.md) | Visão, princípios, mapa das fases, portões, orçamento, cronograma |
| [Fase 0 — Desenho e contratos](plano/fase-0-desenho-e-contratos.md) | Decisões políticas, fronteira público/restrito, contratos entre as camadas |
| [Fase 1 — Corpus](plano/fase-1-corpus.md) | Ingestão, metadados, direitos, anonimização |
| [Fase 2 — Protótipo](plano/fase-2-prototipo.md) | **Fase atual.** RAG, benchmark de modelos, primeira redação do marco |
| [Fase 3 — Avaliação e servidor](plano/fase-3-avaliacao-e-servidor.md) | Casos-teste, métricas por camada, hardware próprio |
| [Fase 4 — Especialização](plano/fase-4-especializacao.md) | Ajuste fino (LoRA), condicional |
| [Fase 5 — Abertura e sustentação](plano/fase-5-abertura-e-sustentacao.md) | Publicação, replicação, manutenção |
| `plano/IPF - Projeto desenvolvimento IA Freiriana.pdf` | Documento de origem. Fica na máquina, **não é versionado** aqui |

Nos outros documentos, as fases aparecem abreviadas: "`fase-3` §7" quer dizer a seção 7 de
[Fase 3](plano/fase-3-avaliacao-e-servidor.md).

## `engenharia/` — o que está construído, e por quê

| Documento | Função | Atualiza quando |
|---|---|---|
| [Arquitetura](engenharia/arquitetura.md) | Como o código se organiza: camadas, fluxo de uma pergunta, contratos, onde cada coisa mora. **Sem números** | muda a estrutura, um contrato ou o fluxo |
| [Medições](engenharia/medicoes.md) | O caderno de medições: cada número que justifica um padrão, com data e comando, e os caminhos rejeitados | um número é produzido ou invalidado |

## `acervo/` — como o acervo do Centro de Referência vai entrar

O acervo real é um repositório DSpace cujos metadados não serão alterados. Um documento analisa o
que eles permitem; o outro propõe o esquema que sai dessa análise.

| Documento | Função |
|---|---|
| [Limites dos metadados do acervo](acervo/limites-dos-metadados-do-acervo.md) | **Diagnóstico.** O que os metadados do DSpace permitem e impedem, em ordem de gravidade, e o veredito sobre cada funcionalidade do plano |
| [Esquema de metadados](acervo/esquema-de-metadados.md) | **Proposta (v0.2, não aprovada).** O que cada documento e cada chunk carregam, de onde vem cada campo, e as decisões pendentes com dono (§11) |

## Fora de `docs/`

| Documento | Função |
|---|---|
| [README do repositório](../README.md) | Porta de entrada: o que é, instalação, comandos, container |
| [`CLAUDE.md`](../CLAUDE.md) | Instrução para o assistente de código: comandos e armadilhas. Importa as [diretrizes](diretrizes.md) |
| [`marcos/LEIA-ME.md`](../marcos/LEIA-ME.md) | Instrução para o comitê pedagógico editar os marcos |
