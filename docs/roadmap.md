# Roadmap do software

> [Índice dos documentos](README.md) · [Diretrizes](diretrizes.md) · [Medições](engenharia/medicoes.md) · [Plano geral](plano/00-plano-geral-implementacao.md)

**Última atualização:** 2026-10-07 · 346 testes · fase do plano: **Fase 2 — protótipo**

## Para que serve este documento

Diz **o que o software precisa fazer, o que já faz e o que falta**, do protótipo até a
sustentação. É o documento a ler antes de decidir o que implementar em seguida.

- **Cobre:** o código deste repositório (`src/`, `marcos/`, `avaliacao/`, `tests/`) e o que as
  fases do [plano](plano/00-plano-geral-implementacao.md) pedem dele.
- **Não cobre:** o andamento institucional (comitê, catalogação do acervo, parceria, compra de
  hardware). Quando um item depende disso, a coluna "destravado por" diz de quem.
- **Não traz números.** O porquê de cada padrão em vigor, com as medições, está em
  [medições](engenharia/medicoes.md). Aqui aparece só o link.
- **Quando atualizar:** ao terminar, começar ou descartar um item; ao mudar um padrão em vigor.

Legenda: ✅ pronto · 🟡 parcial ou provisório · ⬜ não começado · ⏸ espera outra pessoa

---

## 1. Onde estamos

O pipeline completo roda localmente sobre um **corpus descartável** (lore da UESP), que existe só
para exercitar o código com volume real até o acervo do IPF ficar pronto. As camadas próprias do
projeto — sessão dialógica, mediação, marco e memória de conversa — estão implementadas e medidas.
O que separa o protótipo do portão G2 → 3 é, sobretudo, trabalho que não é de código (§3).

**Padrões em vigor**, conferíveis com `python3 main.py config`:

| Parâmetro | Valor | Por quê |
|---|---|---|
| `chunking.estrategia` | `paragrafo_agrupado`, teto 2000 | [medições § tamanho do recorte](engenharia/medicoes.md#tamanho-do-recorte--agrupado-de-2000-vence-2026-10-05) |
| `vetorial.colecao` | `uesp_lore_agrupado_2000` | idem |
| `busca.reordenar` / `busca.k` | `true` / 8 | [medições § mediação](engenharia/medicoes.md#mediação--de-3-pontos-a-2-depois-de-quatro-correções) |
| `busca.limiar_relativo` | 0,90 — só atua com `--sem-reordenar` | [medições § política de recuperação](engenharia/medicoes.md#escolha-da-política-de-recuperação) |
| `busca.hibrido` | `false` | [medições § BM25](engenharia/medicoes.md#bm25-híbrido--depende-do-idioma-e-o-peso-do-rrf-decide) |
| `intermediacao.decompor` | `true` | [medições § mediação](engenharia/medicoes.md#mediação--de-3-pontos-a-2-depois-de-quatro-correções) |
| `geracao.num_ctx` | 8192 | [medições § janela](engenharia/medicoes.md#janela-de-contexto) |
| `marco.ativo` | `generico` | o `freiriano` é esqueleto (§2) |
| carga | `total` (o `reduzida` é experimental) | [medições § limitador](engenharia/medicoes.md#limitador-de-carga--poupar-o-hardware-de-dentro-do-app-2026-10-05) |

---

## 2. O que está pronto

| Capacidade | O que faz | Onde |
|---|---|---|
| ✅ Pipeline | download → chunking → indexação → recuperação → geração, cada etapa refazível sozinha | `src/rag/etapas/` |
| ✅ Indexação retomável | pula chunks já indexados; confere a dimensão do vetor antes de processar | `etapas/indexacao.py` |
| ✅ Proveniência por chunk | campos `pagina`, `secao`, `inicio`, `fim`, `versao_embedding`, `restricao_uso` existem e viajam no payload — **vazios** até o acervo real | `modelos.py` |
| ✅ Ciclo RAG | recuperação + orçamento de contexto + geração com citação | `orquestrador.py` |
| ✅ Validação de citações | confere se cada `[Fonte N]` existe no que foi ao modelo | `etapas/geracao.py` |
| ✅ Reordenação | cross-encoder sobre a lista fundida, uma vez por pergunta | `clientes/`, `servico.py` |
| ✅ Busca híbrida BM25 | implementada, **desligada por padrão** | `lexico.py` |
| ✅ Marco pedagógico | carrega, valida e aplica `marcos/*.md`; marco quebrado levanta erro | `marco.py` |
| ✅ Mediação de consulta | decompõe pergunta composta, funde por RRF | `mediacao.py` |
| ✅ Sessão dialógica | triagem e problematização antes de responder | `sessao.py` |
| ✅ Memória de conversa | reescreve o seguimento; histórico só em memória, nunca gravado | `conversa.py` |
| ✅ Avaliação da recuperação | `recall@k`, cobertura, MRR e cortes do orçamento, sem gerar texto | `avaliacao.py` |
| ✅ Configuração em camadas | padrões → `config.toml` → flags, com a origem de cada valor | `config.py` |
| ✅ Duas portas | menu e CLI chamam as mesmas ações | `interface/` |
| ✅ Container | aplicação em container; variante com GPU para o reordenador | `compose.yaml`, `Containerfile` |
| ✅ Regras de modularidade testadas | a suíte falha se uma etapa importar outra ou um cliente | `tests/test_estrutura.py` |
| 🟡 Modos de carga | `total` pronto; `reduzida` **experimental** (picos não explicados, §4 item 1) | `carga.py` |

### Provisório — existe, mas no lugar de outra coisa

| Item | Estado | Destravado por |
|---|---|---|
| 🟡 Corpus UESP | descartável, 8896 páginas de lore | ⏸ catalogação do acervo do IPF (Fase 1) |
| 🟡 `marcos/generico.md` | ativo por padrão, sem valor pedagógico | ⏸ o marco freiriano ficar pronto |
| ⏸ `marcos/freiriano.md` | esqueleto, `versao: 0` — só as perguntas de cada seção | ⏸ redação do comitê ([fase 2](plano/fase-2-prototipo.md) §4.6). **Não cabe a programadores** |
| 🟡 `avaliacao/casos.jsonl` | 40 casos da equipe técnica sobre o corpus descartável | ⏸ os 80–150 casos do comitê ([fase 3](plano/fase-3-avaliacao-e-servidor.md) §4) |
| 🟡 `avaliacao/casos_conversa.jsonl` | 16 seguimentos da equipe técnica | ⏸ seguimentos reais, do registro de uso |

---

## 3. Fase 2 — o que falta para o portão G2 → 3

Os critérios de aceite de [fase 2](plano/fase-2-prototipo.md) §6, um a um, do ponto de vista do
software.

| Critério do plano | Estado | O que falta |
|---|---|---|
| 3–4 modelos testados com o mesmo conjunto de perguntas | ⬜ | Só o `qwen2.5:7b` foi usado. Falta um modo de benchmark de **gerador**: mesmas perguntas, mesma temperatura, mesmo índice, saídas gravadas para comparação humana (§4 item 2) |
| Cita fonte com documento e página verificáveis | 🟡 | Documento sim; página não, porque o corpus UESP não tem página. Entra com o acervo (§5) |
| Filtro de restrição de uso dentro da query | ⬜ | Nada implementado. Desenho em [esquema](acervo/esquema-de-metadados.md) §8.3 (§5) |
| `recall@k` medível sem gerar texto | ✅ | — |
| Marco em primeira redação, escrito pelo comitê | ⏸ | Comitê |
| Marco fora do código, versionado | ✅ | — |
| Relatório crítico de uso do piloto | ⬜ / ⏸ | Do lado do software, falta o **registro de uso** com formato fixo ([fase 2](plano/fase-2-prototipo.md) §4.7). Bloqueado por decisão: gravar interação é retenção de dado pessoal (§7) |
| Instalação documentada | ✅ | [README](../README.md) |
| Open WebUI declarado descartável | — | Não se aplica: o protótipo tem orquestração e interface próprias desde o início, que é o que [fase 2](plano/fase-2-prototipo.md) §4.2 queria proteger. Divergência com o plano, registrada aqui |

Duas exigências do plano que não são critério de portão, mas são da Fase 2:

- **Mostrar posições divergentes** ([fase 2](plano/fase-2-prototipo.md) §4.6) — hoje nada no
  ranking diversifica. É o MMR (§4 item 3).
- **Runtime compatível com a API da OpenAI** ([fase 0](plano/fase-0-desenho-e-contratos.md)
  §3.5) — o código fala a API nativa do Ollama. Contornável, registrado em
  [arquitetura](engenharia/arquitetura.md) §5.

---

## 4. Próximos itens, em ordem

Nenhum destes invalida o índice padrão. Os que invalidam esperam a troca de corpus (§5).

| # | Item | Estado | Destravado por |
|---|---|---|---|
| 1 | Entender os picos de 200–250 W da indexação longa em carga reduzida, e só então tirar o "experimental" | ⬜ | Indexar com monitor de sysfs e duração de cada lote ([medições](engenharia/medicoes.md#limitador-de-carga--poupar-o-hardware-de-dentro-do-app-2026-10-05)) |
| 2 | **Benchmark de modelos geradores** — `avaliar` para geração: grava as respostas de N modelos ao mesmo gabarito, sem pontuar (a pontuação é humana) | ⬜ | Nada técnico. É critério do portão G2 → 3 |
| 3 | **MMR** — diversificação contínua do ranking, depois do reordenador | ⬜ | `buscar(..., com_vetores=True)` no protocolo |
| 4 | **Histórico de avaliações** — gravar cada rodada de `avaliar` com configuração, commit e data, para comparar ao longo do tempo ([fase 3](plano/fase-3-avaliacao-e-servidor.md) §6) | ⬜ | Nada |
| 5 | Remedir o BM25 híbrido depois do conserto da quantidade, e decidir o padrão (§7) | ⬜ | Rodar `avaliar --comparar --hibrido` |
| 6 | Avaliação camada 2 — suporte de software à rubrica humana: exportar pergunta, trechos e resposta para quem avalia | ⬜ | ⏸ rubrica do comitê ([fase 3](plano/fase-3-avaliacao-e-servidor.md) §5) |

---

## 5. Na troca para o acervo do IPF — tudo junto, numa reindexação só

A troca de corpus obriga a reindexar. Por isso **toda mudança que invalida o índice espera por ela
e entra junto** ([diretrizes](diretrizes.md), regra 4.3). Esta seção é a lista do que entra nessa
janela.

| # | Item | Muda | Detalhe |
|---|---|---|---|
| 1 | Etapa `etapas/catalogo.py`: lê a exportação do DSpace e as tabelas de política, grava `data/catalogo.jsonl` | nova etapa | [esquema](acervo/esquema-de-metadados.md) §8.4, [arquitetura](engenharia/arquitetura.md) §9 |
| 2 | Download do acervo no lugar do `ColetorUESP`; coleção `corpus_ipf` | etapa, configuração | |
| 3 | **Filtro de `restricao_uso` dentro da query**, por lista de permitidos — falha fechada | protocolo `RepositorioVetorial` | [esquema](acervo/esquema-de-metadados.md) §8.3 |
| 4 | `pagina` e `uri` no `TrechoRecuperado`; citação vira link verificável | payload | [esquema](acervo/esquema-de-metadados.md) §8.4 |
| 5 | `versao_embedding` preenchida em cada chunk | payload | [fase 1](plano/fase-1-corpus.md) §4.8 |
| 6 | Triagem automática de dados pessoais na ingestão | nova regra | ⏸ decisão da direção ([limites](acervo/limites-dos-metadados-do-acervo.md) §2.6) |
| 7 | **Corte por seção** (A1) — reconhece cabeçalhos wikitexto e markdown e preenche `secao`, `inicio`, `fim` | estratégia de chunking | abaixo |
| 8 | **Enriquecimento de contexto** (A4) — embute `título › seção` + texto, exibe só o texto | vetores | abaixo; só rende com A1 |
| 9 | Conferir `chunking.tamanho_maximo` e `reordenacao.tamanho_maximo` contra o corpus novo | configuração | [medições § corpus](engenharia/medicoes.md#corpus-e-índice) |
| 10 | Reescrever `avaliacao/casos.jsonl` sobre o acervo, referenciando o handle em vez do título | gabarito | ⏸ comitê |

**Antes de tudo isso:** o esquema de metadados precisa sair da versão 0.x. Ele não deve ser usado
para indexar enquanto não for aprovado, e as decisões que o destravam estão no
[esquema](acervo/esquema-de-metadados.md) §11, cada uma com o dono dela.

### Os caminhos de recorte que ficam para essa janela

O corte padrão (`paragrafo_agrupado`) resolveu o descarte de parágrafo curto e venceu nas
medições. Dois defeitos continuam: o trecho **não sabe em que seção está**, e o corte segue a linha
em branco, **não a unidade de argumento** — o que [fase 1](plano/fase-1-corpus.md) §4.6 diz que
mais custa num texto de Freire.

- **A1 — corte por seção.** Reconhece `^(={2,6})\s*(.+?)\s*=*$` (wikitexto) e `^(#{2,6})\s+(.+)$`
  (markdown, formato provável da extração de PDF). Seção acima do teto cai no
  `dividir_paragrafo_gigante` que já existe. Exige que o corte devolva, além do texto, o caminho de
  seção e os offsets — interno à etapa, sem mudar `modelos.py`. Testável já: os `.txt` da UESP
  preservam os cabeçalhos `== Seção ==` (conferido em `Lore_Aedra.txt`). **Adiado** porque só
  24% dos arquivos têm cabeçalho ([medições § rejeitados](engenharia/medicoes.md#a1-corte-por-seção--adiado)).
- **A4 — enriquecimento de contexto.** `Chunk.texto_para_embutir()`, usado só na indexação, para
  não sujar a citação mostrada. Sem A1 não há o que prefixar.
- **A2 — janela deslizante** e **A3 — pai/filho**: depois, e só com medição. A2 aumenta os chunks
  em 25–40% e a redundância no top-k; faz sentido dentro de uma seção, depois de A1. A3 tem o maior
  retorno esperado em obra teórica longa, mas exige mudar o protocolo (`obter_por_ids`) ou guardar
  o texto do pai no payload.
- **Contextual retrieval** — prefixo de contexto por chunk gerado por modelo. Uma chamada por
  chunk; avaliar contra A4, que faz parte do mesmo efeito de graça.

---

## 6. Depois da Fase 2 — o que as fases seguintes pedem do software

Itens conhecidos, ainda sem ordem. Viram linhas do §4 quando a fase correspondente começar.

| Fase | Item | Origem |
|---|---|---|
| 3 | Harness disparado automaticamente por mudança de modelo, embedding, chunking ou **marco** | [fase 3](plano/fase-3-avaliacao-e-servidor.md) §6 |
| 3 | Snapshot de índice e temperatura fixa como parte da rodada de avaliação | [fase 3](plano/fase-3-avaliacao-e-servidor.md) §6 |
| 3 | Migração para o servidor próprio: reindexar lá e comparar com a linha de base | [fase 3](plano/fase-3-avaliacao-e-servidor.md) §11 |
| 3 | Backup do corpus e da camada canônica separado do índice, com restauração testada | [fase 1](plano/fase-1-corpus.md) §5 |
| 3–5 | **Formatos de saída estruturados** — roteiro de escuta, matriz de contradição, temas geradores, perguntas para plenária — com estrutura e validação próprias | [fase 2](plano/fase-2-prototipo.md) §4.6, [fase 5](plano/fase-5-abertura-e-sustentacao.md) §6. ⏸ definição pedagógica |
| 5 | Interface para quem não usa terminal (a atual é menu e CLI) | [fase 5](plano/fase-5-abertura-e-sustentacao.md) §6 |
| 5 | Rotina de troca do modelo-base pelo harness | [fase 5](plano/fase-5-abertura-e-sustentacao.md) §5.2 |
| 4 | Ajuste fino (LoRA) — **condicional e provavelmente desnecessário** | [fase 4](plano/fase-4-especializacao.md) §1 |

---

## 7. Decisões pendentes

| Decisão | De quem | Bloqueia |
|---|---|---|
| Ligar o BM25 híbrido por padrão? Ganha com idioma casado, perde sem; o número precisa ser refeito (§4 item 5) | equipe técnica | nada |
| Gravar o registro de uso do piloto: o quê, onde, por quanto tempo, com que anonimização | direção + comitê | relatório crítico de uso (§3) |
| As decisões do esquema de metadados ([esquema](acervo/esquema-de-metadados.md) §11) | direção, comitê, curadoria | toda a §5 |

---

## Itens descartados

Medidos e piores, ou tornados desnecessários. O motivo e os números estão em
[medições § caminhos rejeitados](engenharia/medicoes.md#caminhos-medidos-e-rejeitados).

- Corte por score absoluto (`score_minimo`) — trecho relevante e irrelevante têm a mesma faixa.
- Teto de trechos por documento — favorecido pela forma de medir, não pela qualidade; o MMR é o
  caminho certo.
- Limitador de carga por rajada longa ou por teto de vazão — ciclo térmico e briga com o governador.
