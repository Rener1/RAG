# Estado do desenvolvimento

> [Índice dos documentos](README.md) · [Arquitetura](arquitetura.md) · [Fase 2 — Protótipo](fase-2-prototipo.md) · [README do repositório](../README.md)

**Última atualização:** 2026-10-07 · 313 testes · commit anterior `837654a`
**Padrões em vigor:** `chunking.estrategia = paragrafo_agrupado` (teto 2000) ·
`vetorial.colecao = uesp_lore_agrupado_2000` · `busca.reordenar = true` (com ela vale `busca.k = 8`;
`limiar_relativo = 0,90` só atua com `--sem-reordenar`) · `intermediacao.decompor = true` ·
`geracao.num_ctx = 8192` · `marco.ativo = generico`

## Como usar este documento

Diz **em que ponto o código deste repositório está**: o que funciona, o que é
provisório e o que falta. Escrito para ser lido antes de decidir o que fazer em
seguida.

**Cobre:** o que está implementado em `src/`, `marcos/`, `avaliacao/` e `tests/`,
com o que dá para verificar rodando um comando.

**Não cobre:** o andamento do projeto IPF fora deste repositório — catalogação do
acervo do Centro de Referência, trabalho do comitê pedagógico, aquisição de
hardware, cronograma. Esses estão nos planos por fase em `docs/`, e o estado
deles não é verificável daqui.

**Quando atualizar:** a cada mudança que altere alguma linha das tabelas abaixo.
Número sem data é impressão; se um valor não puder ser reproduzido pelo comando
indicado, ele saiu de validade.

---

## Pronto

| Camada | O que faz | Onde | Testes |
|---|---|---|---|
| Pipeline | download → chunking → indexação → recuperação → geração | `src/rag/etapas/` | 35 |
| Orquestração | `MotorRag`, o ciclo recuperação + geração | `orquestrador.py` | 10 |
| Marco pedagógico | carrega, valida e aplica marcos de `marcos/*.md` | `marco.py` | 23 |
| Mediação de consulta | reformula, decompõe, funde por RRF, deduplica | `mediacao.py` | 40 |
| Sessão dialógica | triagem, problematização, consulta consolidada | `sessao.py` | 31 |
| Configuração | padrões → `config.toml` → flags, com origem rastreável | `config.py` | 21 |
| Janela de contexto | `num_ctx` explícito e orçamento de trechos | `geracao.py`, `orquestrador.py` | 17 |
| Avaliação (camada 1) | `recall@k`, cobertura, MRR e cortes do orçamento de contexto contra gabarito | `avaliacao.py` | 32 |
| Regras estruturais | as duas regras de modularidade, mecanizadas | `tests/test_estrutura.py` | 3 |
| Limitador de carga | fração de uso por lote e threads de CPU do Ollama, para poupar o hardware | `carga.py` | 18 |

Interface completa nas três portas (menu, CLI, ações) para tudo acima — não
existe capacidade alcançável só por uma delas.

---

## Provisório — e por quê

| Item | Estado | Destravado por |
|---|---|---|
| `marcos/freiriano.md` | **Esqueleto, `versao: 0`.** Só as perguntas que cada seção precisa responder | Redação do comitê pedagógico. [fase-2-prototipo.md](fase-2-prototipo.md) §4.6 é explícito em que não cabe a programadores |
| `marcos/generico.md` | Ativo por padrão, **sem valor pedagógico** — existe para exercitar o mecanismo | O marco freiriano ficar pronto |
| Corpus UESP | Descartável, 8896 páginas de lore | Catalogação do acervo do IPF (Fase 1) |
| `avaliacao/casos.jsonl` | 40 casos escritos pela equipe técnica sobre o corpus descartável | Os 80–150 casos reais do comitê (`fase-3` §4), que vêm do registro de uso do piloto |
| Avaliação camada 2 (geração) | **Não existe, e não por esquecimento** | Rubrica humana (`fase-3` §5). `fase-3` §8: LLM como juiz premia o "freirês" que deveria pegar — só pré-filtro, nunca veredito |

---

## Medições

Todas reproduzíveis pelos comandos indicados. Feitas em 2026-09-01, nesta
máquina (16 GB VRAM, qwen2.5:7b Q4_K_M, bge-m3).

### Um defeito do gabarito, corrigido em 2026-09-01

As primeiras medições usavam um gabarito com erro meu: escrevi as páginas
esperadas a partir do meu modelo do assunto, sem notar que o acervo tem
**páginas-índice** (`Lore:Races`, `Lore:Religions`, `Lore:Gods`,
`Lore:Aedra and Daedra`, `Lore:Mer`) que costumam ser a melhor resposta a uma
pergunta ampla. Um caso esperava `Lore:Tsaesci`, que é só uma página de
desambiguação — o conteúdo está em `Lore:Tsaesci (race)` e `(place)`.

Encontrado a partir de uma pergunta real: "monte um panorama das raças de
Tamriel" não trazia `Lore:Races`, e o gabarito não acusava porque não a pedia.

Seis casos corrigidos, 71 → 78 páginas esperadas. **Todos os números abaixo são
pós-correção**; os anteriores mediam em parte o avaliador, não o sistema.

Regra usada para não cair em circularidade: só entrou página que eu listaria
sabendo que ela existe, julgada **sem olhar se o sistema a recuperou**. Ajustar
gabarito para o que o buscador devolve transforma a métrica em espelho.

### Escolha da política de recuperação

`python3 main.py avaliar --sem-intermediar` · 40 casos · busca direta
Coluna "cortes" = casos em que o orçamento de contexto descartou trecho.

| Política | recall | cobertura | trechos/caso | cortes | pior prompt |
|---|---|---|---|---|---|
| `k` fixo = 5 | 75% | 63% | 5,0 | 0/40 | 2717 tok |
| `k` fixo = 8 | 85% | 72% | 8,0 | 0/40 | 4036 tok |
| `k` fixo = 12 | 85% | 76% | 12,0 | 0/40 | 5062 tok |
| `k` fixo = 20 | 90% | 81% | 19,9 | **2/40** | 7023 tok |
| `k` fixo = 30 | 90% | 81% | 28,1 | **15/40** | 7135 tok |
| dinâmico α=0,92 | 82% | 69% | 7,5 | 0/40 | 4347 tok |
| **dinâmico α=0,90** | **88%** | **74%** | **10,3** | 0/40 | 4784 tok |
| dinâmico α=0,88 | 88% | 76% | 13,0 | 0/40 | 6366 tok |

**Em vigor: quantidade dinâmica em α = 0,90.** Recupera mais que o `k = 12`
fixo (88% contra 85%) gastando menos trechos (10,3 contra 12), e adapta ao tipo
de pergunta — menos fontes para dúvida factual, mais para exploração.

`busca.k = 8` fica como o valor usado quando `limiar_relativo` volta a 0.
Enquanto ele estiver ligado, `main.py config` marca o `k` como sem efeito.

A partir de `k = 20` o orçamento de contexto começa a cortar, e em `k = 30`
corta em 15 dos 40 casos — ali o gargalo deixa de ser a recuperação e passa a
ser a janela.

#### Por que relativo, e não por score absoluto

A versão intuitiva — "recupere tudo acima de um score" — foi medida e **não
funciona neste corpus**:

| | mediana | faixa |
|---|---|---|
| Trechos relevantes | 0,552 | 0,436 – 0,718 |
| Trechos irrelevantes | 0,551 | 0,429 – 0,724 |

As duas distribuições são a mesma: 99% dos trechos irrelevantes pontuam acima do
relevante mais fraco. Não há corte absoluto que separe os dois. Pior, o score do
primeiro colocado varia de 0,526 a 0,724 conforme a pergunta, então um corte
fixo **mata perguntas legítimas**: em 0,55, três dos quarenta casos voltavam
vazios; em 0,60, dez. Por isso `score_minimo` continua em 0.

O limiar relativo escapa disso porque não tenta separar relevante de
irrelevante — só mede onde a lista deixa de se parecer com o próprio topo.

### Mediação — de −3 pontos a +2, depois de quatro correções

`python3 main.py avaliar --comparar` · gabarito corrigido

| Configuração | recall | cobertura | MRR | trechos/caso |
|---|---|---|---|---|
| Busca direta | 88% | 74% | 0,601 | 8,4 |
| **Mediação + reordenação** | **95%** | **79%** | **0,682** | **6,5** |

**Remedido em 2026-10-05, no mesmo índice e mesmo gabarito: 88% / 78% / 0,647**
(busca direta 85% / 72%). Os 95% acima não se reproduziram, e a causa não foi
investigada — o que mudou entre as duas medições está no histórico do git, não aqui.
Comparações novas devem usar a remedição como linha de base.

Por tipo de demanda: `exploracao` sobe de 80% a 90%, `produto_acabado` de 80% a
100%. E entrega **menos** trechos que a busca direta — material melhor
selecionado, prompt menor.

A camada media **negativo** (−3 de recall) até quatro bugs serem corrigidos.
Vale registrar quais, porque três deles eram invisíveis sem o harness:

1. **O corte final não seguia a política de quantidade.** A mediação devolvia 8
   trechos onde a busca direta devolvia 11 — o que sozinho já tornava qualquer
   comparação inválida.
2. **O pool de cada sub-consulta era menor que o teto da política.** Buscar 8 por
   sub-consulta e depois aplicar uma política com teto 20 deixava a política sem
   candidatos.
3. **A guarda de tamanho barrava a tradução.** `minimo_de_caracteres = 25`
   existia para não decompor pergunta curta, mas passou a impedir também de
   traduzi-la: "o que são os Hist?" tem 18 caracteres e ia à busca em português
   contra um acervo em inglês.
4. **A dedup matava a tradução.** Similaridade entre "o que são os Hist?" e
   "what are the Hist?" é **0,974**, acima do limiar de 0,95 — o bge-m3 é
   multilíngue e alinha traduções quase no mesmo vetor. Mas "quase" não é
   "igual", e aqueles 0,026 valem os 5 pontos que a tradução rende. Paráfrase
   inútil e tradução útil ficam ambas em ~0,97, e nenhum limiar separa as duas;
   a saída foi não deduplicar a original contra a sua tradução.

Somado a isso, o prompt precisou de **exemplos** (few-shot): só com a regra em
prosa, o modelo traduzia "Hist" — as árvores sencientes — por "histories",
destruindo o termo de maior sinal da consulta.

Exemplo nomeado: em "monte um panorama das raças de Tamriel", a busca direta traz
`Lore:Races` na 7ª posição, dentro do top-8. A fusão RRF da mediação a **expulsa**
para pôr `Lore:Khajiit`, `Lore:Places` e `Lore:Tamriel` — perde a página mais
no alvo da pergunta.

Ressalvas antes de desligá-la: corpus e gabarito são descartáveis, e `recall@k`
não enxerga diversidade, que é metade do motivo pedagógico da camada (mostrar
posições divergentes, `fase-2` §4.6).

### Efeito do idioma da consulta

O corpus é em inglês e as perguntas em português. Medido nos 40 casos, busca
densa, top-8:

| Consulta | recall | cobertura |
|---|---|---|
| Português | 85% | 75% |
| **Inglês** | **90%** | **80%** |

Cinco pontos, e a causa é conhecida: cenários translíngues ficam
consistentemente abaixo dos monolíngues, com quedas de 14% a 33% medidas para o
próprio bge-m3 em outros estudos. Em 12 casos conferidos um a um, a posição
mediana da página esperada é 2 em português contra 1 em inglês, e o efeito se
concentra nas perguntas amplas ("panorama das raças": 7ª em pt, 2ª em en).

**Ressalva importante:** os 90% são com tradução feita à mão. O qwen2.5:7b
traduzindo sozinho chegou a converter "Hist" (as árvores sencientes) em
"Histories" — nome próprio traduzido é o termo de maior sinal destruído. Com a
instrução de preservar nomes próprios e fundindo com a pergunta original por
RRF, o resultado ficou em 88%/78%: recupera o recall, ganha cobertura, mas não
alcança a tradução humana.

A capacidade existe (`idioma_do_acervo` no frontmatter do marco) e **nenhum marco
a declara hoje** — a mediação está restrita a decompor pergunta composta. É
artefato do corpus descartável: some quando o acervo for em português, e os
números acima **subestimam** um pouco o sistema final.

### Janela de contexto

`ollama ps` · `python3 main.py config`

| Medida | Valor | Como foi obtido |
|---|---|---|
| Janela em uso | **8192** tokens | `num_ctx` explícito; antes o Ollama usava 4096 sem avisar |
| Capacidade do qwen2.5:7b | 32768 tokens | `ollama show qwen2.5:7b` |
| Custo em VRAM de 4096 → 8192 | +0,4 GB (4,7 → 5,1) | `ollama ps` |
| Razão chars/token | **4,1** | `prompt_eval_count` em prompts reais (4,06 com k=3; 4,17 com k=8) |
| Prompt com marco genérico | k=3 → 1114 tok; k=8 → 2112 tok | idem |
| `/api/tokenize` no Ollama 0.33 | não existe (404) | por isso a estimativa é por caracteres |

### Corpus e índice

| Medida | Valor | Verificação |
|---|---|---|
| Páginas | 8896 arquivos, 8817 títulos distintos | `python3 main.py ambiente` |
| Chunks (padrão desde 2026-10-07) | 26808 · sha256 `47ed4084…` · `paragrafo_agrupado`, teto 2000 | `sha256sum data/chunks.jsonl` |
| Tamanho de chunk | mediana 1637 · p10 477 · p90 1996 · máx 2000 chars | passagem sobre o JSONL |
| Chunks anteriores (`paragrafo`) | 69285 · sha256 `a991de28…` · mediana 348 · em `data/chunks_paragrafo.jsonl`, coleção `uesp_lore` | mantidos para comparação |
| Truncamento no embedding | **descartado como risco** | bge-m3 via Ollama só ignora cauda acima de ~8k chars; zero chunks passam disso |

O truncamento silencioso estava marcado como risco em [fase-2-prototipo.md](fase-2-prototipo.md) §7.
Está fechado para o corpus atual — mas a verificação é do par modelo+corpus, e
precisa ser refeita ao trocar qualquer um dos dois.

**Reindexar não custa mais horas.** Com o embedding na GPU, o corpus inteiro (38 M
caracteres) leva ~17 min sem limite e ~30–35 min com `--carga 0.75`. Medido ao
indexar as coleções abaixo.

### Tamanho do recorte — agrupado de 2000 vence (2026-10-05)

`paragrafo_agrupado` junta parágrafos consecutivos até o teto, em vez de descartar
os curtos. Três coleções, mesmo gabarito, mesma configuração (`--carga 0.75`, no
container com GPU para o reordenador):

```bash
python3 main.py --chunks chunks_agrupado_2000.jsonl chunking --estrategia paragrafo_agrupado --tamanho-maximo 2000
python3 main.py --carga 0.75 --chunks chunks_agrupado_2000.jsonl --colecao uesp_lore_agrupado_2000 indexar
python3 main.py --chunks chunks_agrupado_2000.jsonl --colecao uesp_lore_agrupado_2000 avaliar --comparar
```

| Coleção | chunks | mediana | busca direta (k=8) | mediação + reordenação | dinâmico α=0,90 |
|---|---|---|---|---|---|
| `uesp_lore` (`paragrafo`, anterior) | 69285 | 348 ch · ~85 tok | 85% / 72% / 0,604 | 88% / 78% / 0,647 | 88% / 74% · 10,3 trechos · 0 cortes |
| `uesp_lore_agrupado_1000` | 51522 | 832 ch · ~200 tok | 82% / 67% / 0,620 | 90% / 76% / 0,711 | 90% / 79% · 12,3 trechos · 0 cortes |
| **`uesp_lore_agrupado_2000`** | **26808** | **1637 ch · ~400 tok** | **90% / 79% / 0,751** | **95% / 81% / 0,742** | 92% / 80% · 9,0 trechos · **4 cortes** |

Formato: recall / cobertura / MRR. "Cortes" = casos em que o orçamento de contexto
descartaria trecho recuperado — medido pelo harness desde esta rodada.

Leituras:

- **2000 ganha em tudo que pesa**: +5 de recall e +7 de cobertura na busca direta,
  e o MRR sobe de 0,60 para 0,75 — a página certa chega mais perto do topo.
- **O caso que motivou a investigação se resolve**: "monte um panorama das raças de
  Tamriel" traz `Lore:Races` em 7º no recorte atual, 4º no de 1000 e **1º** no de
  2000. No atual o topo era de frases de abertura genéricas ("A collection of
  apparel styles worn by the denizens of Tamriel"), que casam com qualquer
  pergunta ampla por não dizerem nada.
- **1000 não é meio-termo**: perde na busca direta e só ganha com mediação.
- **Com 2000, o `k` dinâmico começa a estourar a janela**: 4 de 40 casos cortados,
  recall no prompt 90% em vez de 92%. Em `k = 8` fixo, zero cortes. Como o caminho
  padrão é reordenação com `k = 8`, os cortes só aparecem com `--sem-reordenar`;
  quem voltar à quantidade dinâmica precisa de `k_maximo` menor ou `num_ctx` maior.

**Por que 2000 e não 512 tokens (~2600 caracteres):** o reordenador trunca cada par
pergunta+trecho em `reordenacao.tamanho_maximo = 512` tokens. Acima de ~2000
caracteres a cauda do recorte sumiria do julgamento dele sem aviso. Subir o teto
exige subir aquele campo junto (o bge-reranker-v2-m3 aceita mais, a custo de tempo).

**Promovido a padrão em 2026-10-07, sem reindexar.** A coleção padrão passou a ser
`uesp_lore_agrupado_2000`, já indexada. `data/chunks.jsonl` agora é o arquivo
agrupado (sha256 `47ed4084…`, conferido byte a byte contra `main.py chunking` com
os padrões novos), e o anterior ficou em `data/chunks_paragrafo.jsonl`. Para
comparar com o corte antigo: `--colecao uesp_lore --chunks chunks_paragrafo.jsonl`.

### Limitador de carga — poupar o hardware de dentro do app (2026-10-05)

`[carga] fracao` e `--carga F`. Depois de cada lote o pipeline descansa
`duração × (1/F − 1)`, num limitador só para o processo inteiro (embutidor,
reordenador e gerador de apoio). Medido na RX 9070 XT lendo `freq1_input`,
`power1_average` e `temp2_input` do sysfs, 40–60 s por modo:

| Modo | vazão | clock | potência mediana / máx | junção |
|---|---|---|---|---|
| sem limite (4 × lote 16) | 38,8k ch/s | 3000 MHz | 298 / 352 W | 74–79 °C |
| rajada 5 s + descanso 5 s | 23,0k | alterna 1237↔3038 | 31 / 338 W | **oscila 48↔77 °C** |
| teto de vazão 20k ch/s (estilo FPS) | 19,9k | 1603 | 96 / 287 W | 49–72 °C |
| **fração 75%, lote 8** | **15,9k** | **1568** | **90 / 112 W** | **48–55 °C** |
| fração 50%, lote 8 | 10,9k | 1232 | 51 / 184 W | 46–57 °C |

- **Descanso longo é ciclo térmico** — a média cai, mas a placa aquece e esfria a
  cada rajada, que é o que fadiga solda. Descanso de frações de segundo faz o
  governador da própria placa baixar clock e tensão, e a temperatura fica estável.
- **Teto de vazão briga com o governador**: o clock baixa, a vazão cai abaixo do
  alvo, o limitador para de descansar e os picos voltam. Rejeitado.
- **Pausa mínima maior não ajuda**: acumular o descanso até 100, 250 ou 500 ms
  subiu o pico de 104 W para 113, 132 e 214 W. A pausa por lote fica.

**CPU.** Nosso processo usa ~1% de um núcleo; quem esquenta a CPU é o
`llama-server` do Ollama, com **~4 núcleos em espera ativa** pela GPU.
`carga.threads_de_cpu` manda `num_thread` em cada requisição:

| `num_thread` | vazão | CPU do Ollama |
|---|---|---|
| padrão | 30,6k ch/s | 419% de um núcleo |
| 2 | 30,7k ch/s | 149% |

Mesma vazão, um terço da CPU. Fica em 0 (padrão do Ollama) até ser medido na
geração; mudar o valor faz o Ollama recarregar o modelo uma vez.

**Em aberto — picos na indexação longa.** Nas duas indexações reais com
`--carga 0.75` (64 min no total), o limitador cumpriu a proporção (descanso de
25% do tempo nas duas), mas a placa ficou em ~80 W só nos primeiros ~25 min; de
17:28 em diante passou a 200–250 W e junção de 82–88 °C, por 40 min seguidos.
Não reproduziu em 150 s do mesmo caminho de código (80 W, 51–59 °C), nem havia
outro processo na GPU (`rocm-smi --showpids`). Hipóteses não testadas: efeito que
só aparece com o tempo (temperatura acumulada mudando a política do governador),
ou trechos do corpus que mudam a duração dos lotes. **Até isso ser entendido, o
limitador não deve ser tratado como garantia de potência em execução longa.**
Para investigar: indexar de novo com o monitor de sysfs e registrar a duração de
cada lote junto com o horário.

### Limiar de redundância da mediação

Cosseno entre consultas curtas **não separa** redundante de distinto:

```
redundantes   0,620 ── 0,988
distintas     0,664 ── 0,893
```

"O que diz a lenda do dragonborn?" contra "lenda dragonborn" dá 0,620 — abaixo
de "história dos dragonborn" contra "poderes dos dragonborn" (0,664), que são
facetas legítimas. Por isso `limiar_de_redundancia = 0.95`: rede de segurança
para quase-duplicatas, não o mecanismo de decidir a quantidade. Quem faz esse
trabalho é o prompt. Não adiante o limiar sem refazer essa medição.

---

### BM25 híbrido — depende do idioma, e o peso do RRF decide

Medido com índice invertido sobre os 69285 chunks. **A primeira medição deu o
resultado errado** por usar RRF com pesos iguais, o que deixa um BM25 fraco
arrastar o denso para baixo. Ponderando o denso:

| Consulta | denso sozinho | híbrido, pesos iguais | híbrido, denso com peso ≥2 |
|---|---|---|---|
| Português (idiomas descasados) | **85%** / 75% | 80% / 77% | 82% / 78% |
| Inglês (idiomas casados) | 90% / 80% | 88% / 78% | **92% / 82%** |

Duas leituras, e elas apontam para lados opostos:

- **Com pergunta e documento em idiomas diferentes, o híbrido perde.** A
  recuperação esparsa depende de o termo coexistir nos dois lados, e entre
  português e inglês quase só os nomes próprios sobrevivem. BM25 sozinho faz 50%.
- **Com idioma casado, o híbrido ganha**: +2 de recall e +2 de cobertura.

Os pesos 2, 3, 5 e 10 dão o mesmo resultado. O BM25 **não dirige** o ranking —
ele complementa: o denso ordena, e o esparso promove o que o denso deixou passar.
Peso igual estragava justamente por dar ao complemento o mesmo voto do principal.

**Implementado e desligado por padrão** (`src/rag/lexico.py`, sem dependência
nova). Medido no pipeline real, com a mediação traduzindo as consultas:

| Configuração | recall | cobertura |
|---|---|---|
| Mediação | 90% | 78% |
| **Mediação + híbrido** | **92%** | **79%** |

Fica desligado por três razões: o ganho é de menos de um caso em 40; custa +37%
de tempo; e **sem tradução ele piora** (88% → 85%), porque volta ao cenário
translíngue. Ligar é `--hibrido` ou uma linha no `config.toml`.

Um bug encontrado ao integrar, e que vale lembrar: cosseno vive perto de 0,6 e
BM25 chega a 10 ou mais, e `fundir_por_rrf` conserva o melhor score original de
cada trecho. Sem reescalar o léxico para a faixa do denso, a política de
quantidade dinâmica — que corta por fração do score do topo — descartava quase
tudo. `trechos/caso` caía de 8,9 para 6,5 e o recall de 92% para 85%.

O acervo do IPF será de idioma casado, e com um agravante a favor: o vocabulário
freiriano ("tema gerador", "conscientização", "práxis") é termo exato e raro, que
é o que o esparso explora e o que o embedding dilui em sinônimos. A wiki de lore
é o oposto: prosa narrativa, com a mesma coisa dita de dez formas.

**Força da evidência:** 90% → 92% em 40 casos é menos de um caso de diferença, e
isoladamente não conclui nada. O que dá alguma confiança é a consistência entre
os quatro pesos e a cobertura subir junto. Refazer com o gabarito do comitê.

---

## Caminhos medidos e **rejeitados**

Cada linha abaixo custou uma medição e poupou uma implementação. Estão aqui para
ninguém refazer o teste, e para o motivo não se perder.

Rejeição aqui significa **medido e pior**, não "não tentamos". Caminho que perde
neste corpus mas deve ganhar no acervo real está na seção do BM25, não nesta.

### Teto de trechos por documento — descartado

Chegou a medir bem (+3 de recall na mediação), mas a métrica é por página, então
uma política que maximiza páginas distintas é favorecida pela forma de medir, não
necessariamente pela qualidade. Cortar para um parágrafo por fonte destrói
resposta que precisa de três trechos da mesma página. MMR é a forma correta de
diversificar, e entra depois do reordenador — que a torna menos necessária.

### A1, corte por seção — adiado

Só **24% dos chunks** vêm de arquivos com cabeçalho de seção (2636 de 8896
arquivos), e `Lore:Races` — a página que motivou a investigação — não tem nenhum.
Os benchmarks ainda medem corte semântico/estrutural **abaixo** de divisão
recursiva simples (54% contra 69% ponta a ponta). Custaria horas de reindexação
para mexer em um quarto do acervo, contra a literatura.

O que a mesma fonte aponta a favor é outra coisa: o tamanho de referência é ~512
tokens, e a **mediana dos nossos chunks é 85 tokens** — de quatro a seis vezes
menor. Esse experimento foi feito em 2026-10-05 e o agrupado de 2000 caracteres
ganhou (ver "Tamanho do recorte").

---

## Pendente, em ordem

| # | Item | Destravado por | Invalida o índice? |
|---|---|---|---|
| 1 | Entender os picos de 200–250 W na indexação longa com `--carga 0.75` | Indexar com monitor de sysfs e duração de cada lote | não |
| 2 | Preencher página e offset nos campos de proveniência do `Chunk` | Troca para o acervo do IPF, que já obriga a reindexar | sim, junto da troca |
| 3 | **MMR** — diversificação contínua, em vez de teto rígido | `buscar(..., com_vetores=True)` no protocolo | não |
| 4 | Ligar o **BM25 híbrido** por padrão | Decidir se +2 de recall paga +37% de tempo | não |
| 5 | **Contextual retrieval** — prefixo de contexto por chunk gerado por LLM | Uma chamada de modelo por chunk (26808) | sim; janela da troca de corpus |
| 6 | Avaliação camada 2 — rubrica e casos reais | Comitê pedagógico + registro de uso do piloto | não |
| 7 | Conferir `chunking.tamanho_maximo` contra corpus novo | Troca de corpus | — |
| 8 | **Metadados do acervo** — etapa de derivação a partir da exportação DSpace, filtro de `restricao_uso` dentro da query, `pagina` e `uri` na citação, `versao_embedding` preenchida, triagem automática de dados pessoais | Aprovação do esquema v0.2 e as decisões de direção de §11 dele | payload sim, vetor não |

Os caminhos A1–A6 estão detalhados em
[recorte-de-conteudo-caminhos.md](recorte-de-conteudo-caminhos.md). O item 8 está detalhado em
[esquema-de-metadados.md](esquema-de-metadados.md) §8.4 — são as dez mudanças de código que o
esquema de metadados do acervo exige, nenhuma delas implementada. O acervo é um repositório DSpace
cujos metadados não serão alterados nem preenchidos; o que isso impede está em
[limites-dos-metadados-do-acervo.md](limites-dos-metadados-do-acervo.md).

**Regra que organiza a coluna da direita:** toda mudança que invalida o índice
espera pela próxima reindexação obrigatória, e todas entram juntas. Reindexar
custava horas; com o embedding na GPU são ~17 min, o que enfraquece a regra para
experimentos em coleção separada, mas não para a coleção padrão.

---

## Decisões pendentes

1. **Ligar o BM25 híbrido por padrão?** Ganha com idioma casado, perde sem. Como
   a mediação hoje traduz, o cenário é o favorável — mas medi antes do conserto
   da quantidade e o número precisa ser refeito.

---

## Invariantes — o que não pode quebrar

```bash
python3 -m unittest discover -s tests -t tests   # 313 testes, sem rede nem serviço
ruff check src/ tests/ main.py                   # lint
python3 main.py ambiente                         # serviços, modelos e artefatos
sha256sum data/chunks.jsonl                      # 47ed4084…  (26808 chunks)
```

1. **Nenhum módulo de `etapas/` importa outro de `etapas/`.**
2. **As etapas dependem de `protocolos.py`, nunca de `clientes/`.**

As duas são verificadas por `tests/test_estrutura.py`, que percorre os módulos
com `ast` — não dependem de ninguém lembrar delas. `marco.py`, `mediacao.py`,
`sessao.py` e `avaliacao.py` ficam na raiz do pacote pelo mesmo motivo de
`orquestrador.py`: compõem recuperação com geração, e isso não pertence a
nenhuma etapa.
