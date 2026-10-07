# Documentação — por onde começar

Os documentos deste repositório se dividem em três grupos:

- **o plano do projeto**, que é institucional e vale além do código;
- **a engenharia**, que descreve o que está construído aqui;
- **o acervo**, que trata de como os documentos do Centro de Referência Paulo Freire vão entrar.

Cada documento abre com uma linha de navegação de volta para cá.

## Por onde começar, conforme o que você procura

| Você quer… | Leia |
|---|---|
| entender o projeto em uma página | [Plano geral](00-plano-geral-implementacao.md) §1 |
| saber em que ponto o código está | [Estado do desenvolvimento](estado-do-desenvolvimento.md) |
| entender como o código é organizado | [Arquitetura](arquitetura.md) |
| instalar e rodar | [README do repositório](../README.md) |
| editar um marco pedagógico (sem programar) | [Como editar um marco](../marcos/LEIA-ME.md) |
| saber o que a fase atual precisa entregar | [Fase 2 — Protótipo](fase-2-prototipo.md) §5–6 |

## O plano do projeto

A sequência de fases, com portões de entrada e saída, papéis e orçamento. Vem do documento de
origem do Instituto Paulo Freire, que fica fora do repositório. Quando o plano e o código
divergem, o plano diz o que se quer, e o [estado](estado-do-desenvolvimento.md) diz o que se tem.

| Documento | Do que trata |
|---|---|
| [00 — Plano geral](00-plano-geral-implementacao.md) | Visão, princípios, mapa das fases, portões, orçamento, cronograma |
| [Fase 0 — Desenho e contratos](fase-0-desenho-e-contratos.md) | Decisões políticas, fronteira público/restrito, contratos entre as camadas |
| [Fase 1 — Corpus](fase-1-corpus.md) | Ingestão, metadados, direitos, anonimização |
| [Fase 2 — Protótipo](fase-2-prototipo.md) | **Fase atual.** RAG, benchmark de modelos, primeira redação do marco |
| [Fase 3 — Avaliação e servidor](fase-3-avaliacao-e-servidor.md) | Casos-teste, métricas por camada, hardware próprio |
| [Fase 4 — Especialização](fase-4-especializacao.md) | Ajuste fino (LoRA), condicional |
| [Fase 5 — Abertura e sustentação](fase-5-abertura-e-sustentacao.md) | Publicação, replicação, manutenção |

Nos outros documentos, as fases aparecem abreviadas: "`fase-3` §7" quer dizer a seção 7 de
[Fase 3](fase-3-avaliacao-e-servidor.md).

## A engenharia

| Documento | Do que trata |
|---|---|
| [Arquitetura](arquitetura.md) | Como o código é organizado: camadas, fluxo de uma pergunta, contratos, onde cada coisa mora, e o porquê |
| [Estado do desenvolvimento](estado-do-desenvolvimento.md) | O que está pronto, o que é provisório, o que falta, e **todas as medições**. É o que se atualiza a cada mudança |
| [Recorte de conteúdo — caminhos](recorte-de-conteudo-caminhos.md) | As alternativas de chunking (A1–A6), o custo de cada uma e a ordem recomendada |
| [README do repositório](../README.md) | Instalação, comandos, container |

## O acervo

O acervo real é um repositório DSpace cujos metadados não serão alterados. Os dois documentos
abaixo dizem o que dá para derivar dele e o que não dá.

| Documento | Do que trata |
|---|---|
| [Esquema de metadados](esquema-de-metadados.md) | O que cada documento e cada chunk carregam, de onde vem cada campo, e o que falta decidir (§11) |
| [Limites dos metadados do acervo](limites-dos-metadados-do-acervo.md) | O que os metadados do DSpace permitem e o que impedem, em ordem de gravidade |

## Fora de `docs/`

| Documento | Do que trata |
|---|---|
| [`marcos/LEIA-ME.md`](../marcos/LEIA-ME.md) | Instrução para o comitê pedagógico editar os marcos |
| [`CLAUDE.md`](../CLAUDE.md) | Orientação para o assistente de código: regras, armadilhas, comandos. Útil também para pessoas, mas escrito como instrução |
| `docs/IPF - Projeto desenvolvimento IA Freiriana.pdf` | Documento de origem do Instituto. Não é versionado aqui |
