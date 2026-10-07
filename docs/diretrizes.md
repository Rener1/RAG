# Diretrizes de desenvolvimento

> [Índice dos documentos](README.md) · [Roadmap](roadmap.md) · [Arquitetura](engenharia/arquitetura.md) · [Plano geral](plano/00-plano-geral-implementacao.md) §2

**Versão:** 0 — **rascunho para a equipe preencher** · 2026-10-07

## Para que serve este documento

Diz **como se trabalha neste repositório**: as regras que valem para qualquer mudança, seja de
uma pessoa, seja do assistente de código. O [roadmap](roadmap.md) diz *o que* fazer; este
documento diz *como*.

Os [cinco princípios do plano geral](plano/00-plano-geral-implementacao.md) (§2) estão acima
destas diretrizes: se uma delas conflitar com um princípio, o princípio ganha. O `CLAUDE.md`
importa este arquivo, e por isso as regras abaixo valem também para o assistente.

**Como ler a coluna de origem:**

- **pedido** — dito pela equipe no início do projeto;
- **testado** — em vigor, e a suíte de testes falha se for quebrado;
- **praticado** — em vigor e seguido no código, mas sem verificação automática;
- **plano** — exigido por um documento do [plano](plano/00-plano-geral-implementacao.md);
- **proposta** — sugestão a partir do que o projeto já faz, **a confirmar, ajustar ou riscar**.

---

## 1. Modularidade

O sistema deve ser **totalmente modular**: cada peça que pode mudar fica atrás de um contrato, e
trocar a peça não mexe no resto.

| # | Diretriz | Origem | Como se verifica |
|---|---|---|---|
| 1.1 | Toda peça substituível (banco vetorial, modelo, coletor de corpus, reordenador) fica atrás de um protocolo em `protocolos.py`. Trocar a peça é escrever outra classe e mudar uma linha em `servico.py` | pedido | revisão |
| 1.2 | Nenhum módulo de `etapas/` importa outro módulo de `etapas/`. Etapas conversam por artefato em disco | testado | `tests/test_estrutura.py` |
| 1.3 | As etapas dependem de `protocolos.py`, nunca de `clientes/` | testado | `tests/test_estrutura.py` |
| 1.4 | Código que compõe recuperação com geração mora na raiz do pacote, não em `etapas/` | praticado | revisão |
| 1.5 | Um ponto de entrada só (`main.py`). Toda capacidade nova vira uma ação em `interface/acoes.py`, ligada no menu **e** na CLI | praticado | revisão |
| 1.6 | Comportamento pedagógico é dado (`marcos/*.md`), nunca texto de prompt no código | plano ([fase 0](plano/fase-0-desenho-e-contratos.md) §3.5) | revisão |
| 1.7 | Trocar de modelo é mudar configuração, não código | plano (princípio 2) | `main.py config` |
| 1.8 | Toda camada opcional pode ser desligada por flag, e é assim que se mede o efeito dela | praticado | `--sem-intermediar`, `--direto`, `--sem-memoria` |

## 2. Código

Seguir **sempre as boas práticas de desenvolvimento** — e, para não ficar no genérico, estas
são as que valem aqui.

| # | Diretriz | Origem | Como se verifica |
|---|---|---|---|
| 2.1 | Código inteiro em português brasileiro: nomes, docstrings, comentários e saída | praticado | revisão |
| 2.2 | `ruff format` e `ruff check` limpos antes de cada commit | praticado | `ruff check src/ tests/ main.py` |
| 2.3 | Testes rodam sem serviço externo nem rede. Dependência externa entra como dublê em `tests/apoio.py` | testado | a suíte roda em menos de 1 s |
| 2.4 | Mudança de protocolo atualiza o dublê correspondente no mesmo commit | praticado | a suíte |
| 2.5 | Toda funcionalidade nova chega com teste; todo defeito corrigido chega com o teste que o teria pegado | proposta | revisão |
| 2.6 | Os padrões ficam em `config.py`, cada um com o comentário que diz **por que** vale aquilo. Nada de valor mágico espalhado pelos módulos, nada em `.env` | praticado | revisão |
| 2.7 | Camada opcional que tropeça vira o caminho mais simples, nunca exceção (a mediação falha → busca direta). Dado obrigatório quebrado **falha alto** (marco inválido levanta erro) | praticado | testes de cada camada |
| 2.8 | Erro mostrado ao usuário diz o que fazer para consertar (`erros.py`, campo `sugestao`) | praticado | revisão |
| 2.9 | Mudança de formato de artefato é aditiva: campo novo vazio não é gravado, e o `chunks.jsonl` existente continua byte a byte idêntico | praticado | `sha256sum data/chunks.jsonl` |
| 2.10 | Dependência nova só com justificativa escrita; preferir a biblioteca padrão (o BM25 foi escrito sem dependência nova) | proposta | revisão do `requirements.txt` |
| 2.11 | Ferramenta de amplo uso antes de solução elegante e obscura — mitiga a dependência de uma pessoa só | plano ([fase 3](plano/fase-3-avaliacao-e-servidor.md) §12) | revisão |
| 2.12 | Commits pequenos, um assunto cada, no formato `tipo(escopo): descrição` em português | praticado | `git log` |

## 3. Documentação

A **documentação deve ser sempre consultada e atualizada**. Concretamente:

| # | Diretriz | Origem | Como se verifica |
|---|---|---|---|
| 3.1 | Antes de mudar: ler o [roadmap](roadmap.md) e a parte da [arquitetura](engenharia/arquitetura.md) que a mudança toca | pedido | — |
| 3.2 | A documentação muda **no mesmo commit** que o código que ela descreve (tabela abaixo) | pedido | revisão |
| 3.3 | Cada fato mora num documento só; os outros apontam para ele. Número duplicado em dois lugares é número que vai divergir | praticado | revisão |
| 3.4 | Todo documento abre com a linha de navegação, diz para que serve, e está no [índice](README.md). Documento sem função própria é fundido a outro ou apagado | pedido | revisão |
| 3.5 | Os documentos de [`plano/`](plano/) são institucionais: não se editam para refletir o código. Quando o código diverge do plano, a divergência é registrada no roadmap ou na arquitetura | praticado | — |
| 3.6 | Instalação e operação se documentam enquanto se instala, não depois | plano ([fase 2](plano/fase-2-prototipo.md) §4.1) | — |

**Onde cada coisa é atualizada:**

| Se a mudança… | Atualize |
|---|---|
| termina, começa ou descarta um item; muda um padrão em vigor | [roadmap](roadmap.md) |
| produz ou invalida um número | [medições](engenharia/medicoes.md), com data e comando |
| muda a organização do código, um contrato ou o fluxo de uma pergunta | [arquitetura](engenharia/arquitetura.md) |
| muda um comando, uma flag ou a instalação | [README](../README.md) e a lista de comandos do `CLAUDE.md` |
| cria uma armadilha que custou tempo para descobrir | `CLAUDE.md`, seção "Armadilhas" |
| muda o que se espera do acervo | [esquema de metadados](acervo/esquema-de-metadados.md), com nova linha no registro de alterações |
| acrescenta um campo de configuração | regere o `config.exemplo.toml` (há teste que falha se ficar defasado) |

## 4. Medição e decisões técnicas

| # | Diretriz | Origem | Como se verifica |
|---|---|---|---|
| 4.1 | Nenhum padrão muda sem medição. Número registrado leva **data e o comando que o reproduz**; número sem isso é impressão | praticado | [medições](engenharia/medicoes.md) |
| 4.2 | Recuperação e geração se medem separadamente — têm correções opostas. Ao depurar resposta ruim, conferir a recuperação (`buscar`) antes de mexer no prompt | plano ([fase 3](plano/fase-3-avaliacao-e-servidor.md) §7) | `avaliar` não gera texto |
| 4.3 | Mudança que invalida o índice padrão espera a próxima reindexação obrigatória, e todas entram juntas. Experimento usa `--saida` e `--colecao` próprios e não toca nos artefatos padrão | praticado | [roadmap](roadmap.md) §5 |
| 4.4 | O gabarito nunca é ajustado ao que o buscador devolveu: isso transforma a métrica em espelho | praticado | revisão de `avaliacao/` |
| 4.5 | Qualidade de resposta é rubrica humana. Modelo como juiz só como pré-filtro, nunca como veredito — ele premia o "freirês" | plano ([fase 3](plano/fase-3-avaliacao-e-servidor.md) §8) | `avaliacao.py` não tem métrica textual |
| 4.6 | Caminho medido e rejeitado é registrado com o motivo, para ninguém refazer o teste | praticado | [medições](engenharia/medicoes.md#caminhos-medidos-e-rejeitados) |
| 4.7 | Não otimizar para o corpus descartável. Ajuste que só faz sentido para a lore da UESP não vira padrão; o que importa é o que vai valer no acervo do IPF | proposta | revisão |

## 5. Dados, segurança e papéis

| # | Diretriz | Origem | Como se verifica |
|---|---|---|---|
| 5.1 | Restrição de uso falha **fechada**: na dúvida, o documento não é recuperado. O filtro é por lista de permitidos e roda dentro da query | plano ([esquema](acervo/esquema-de-metadados.md) §8.3) | ainda não implementado |
| 5.2 | Material restrito nunca sai para infraestrutura de terceiros | plano ([fase 0](plano/fase-0-desenho-e-contratos.md) §3.4) | — |
| 5.3 | Nada da conversa do usuário é gravado em disco. Gravar é decisão de retenção de dado pessoal, e não cabe à equipe técnica tomar sozinha | praticado | `conversa.py` |
| 5.4 | Programadores não escrevem o conteúdo do marco freiriano nem os casos-teste reais: são do comitê pedagógico, que tem veto sobre o comportamento do sistema | plano (princípio 1, [fase 2](plano/fase-2-prototipo.md) §4.6) | revisão de `marcos/` |
| 5.5 | Toda resposta cita fonte verificável, e a citação é validada contra o que foi de fato ao modelo | plano (princípio 4) | `validar_citacoes` |

---

## 6. Para preencher

Pontos em que o projeto ainda não tem regra. Cada um merece uma linha numa das tabelas acima,
ou uma decisão explícita de que não precisa.

1. **Fluxo de branches.** Hoje tudo vai direto para `master`. Branch por funcionalidade com
   revisão antes de juntar, ou commit direto enquanto a equipe técnica for de uma pessoa?
2. **Revisão.** Quem revisa uma mudança antes de ela entrar — outra pessoa, o assistente
   (`/code-review`), ou ninguém por enquanto?
3. **Tipagem.** O código usa anotações de tipo em todo lugar. Vale exigir com verificador
   (`mypy` ou `pyright`), ou basta a convenção?
4. **Ambiente Python.** A instalação é global, sem virtualenv, em Python 3.14. Fixar versões no
   `requirements.txt`? Declarar a versão mínima de Python?
5. **Versões e entregas.** Marcar com tag (`v0.1`, …) os pontos em que o protótipo foi mostrado
   ao comitê, para poder voltar a eles?
6. **Gatilho do harness.** [Fase 3](plano/fase-3-avaliacao-e-servidor.md) §6 pede avaliação a
   cada mudança de modelo, embedding, chunking ou marco. Até haver automação, a regra é rodar
   `avaliar --comparar` à mão nesses casos e registrar em medições?
7. **Tamanho de mudança.** Há limite para o que entra num commit só, ou para o tamanho de um
   módulo antes de ele ser dividido?
8. **Uso do assistente de código.** O que ele pode fazer sem perguntar (rodar testes, editar
   código) e o que exige confirmação (indexar, baixar corpus, commit, push)?
