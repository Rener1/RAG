# Estado do desenvolvimento

**Última atualização:** 2026-09-02 · 289 testes · commit anterior `fa3d7c8`
**Padrões em vigor:** `busca.limiar_relativo = 0,90` (quantidade dinâmica) · `busca.k = 8` (reserva) ·
`busca.reordenar = false` · `intermediacao.decompor = true` ·
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
| Avaliação (camada 1) | `recall@k`, cobertura e MRR contra gabarito | `avaliacao.py` | 28 |
| Regras estruturais | as duas regras de modularidade, mecanizadas | `tests/test_estrutura.py` | 3 |

Interface completa nas três portas (menu, CLI, ações) para tudo acima — não
existe capacidade alcançável só por uma delas.

---

## Provisório — e por quê

| Item | Estado | Destravado por |
|---|---|---|
| `marcos/freiriano.md` | **Esqueleto, `versao: 0`.** Só as perguntas que cada seção precisa responder | Redação do comitê pedagógico. `docs/fase-2-prototipo.md` §4.6 é explícito em que não cabe a programadores |
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
| Chunks | 69285 · sha256 `a991de28…` | `sha256sum data/chunks.jsonl` |
| Tamanho de chunk | mediana 348 · p90 1466 · p99 1999 · máx 2000 chars | passagem sobre o JSONL |
| Truncamento no embedding | **descartado como risco** | bge-m3 via Ollama só ignora cauda acima de ~8k chars; zero chunks passam disso |

O truncamento silencioso estava marcado como risco em `fase-2-prototipo.md` §7.
Está fechado para o corpus atual — mas a verificação é do par modelo+corpus, e
precisa ser refeita ao trocar qualquer um dos dois.

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
menor. É esse o experimento que vale, e ele está pendente.

---

## Pendente, em ordem

| # | Item | Destravado por | Invalida o índice? |
|---|---|---|---|
| 1 | **Tamanho de chunk** — testar ~512 tokens contra os 85 atuais | Nada; `paragrafo_agrupado` já existe e o harness já mede | **sim** — coleção separada |
| 2 | **Tamanho de chunk** — testar ~512 tokens contra os 85 atuais | Nada; `paragrafo_agrupado` já existe e o harness já mede | **sim** — roda em coleção separada |
| 3 | Preencher página e offset nos campos de proveniência do `Chunk` | Troca para o acervo do IPF, que já obriga a reindexar | sim, junto da troca |
| 4 | **MMR** — diversificação contínua, em vez de teto rígido | `buscar(..., com_vetores=True)` no protocolo | não |
| 5 | Ligar o **BM25 híbrido** por padrão | Decidir se +2 de recall paga +37% de tempo | não |
| 6 | **Contextual retrieval** — prefixo de contexto por chunk gerado por LLM | Uma chamada de modelo por chunk (69285) | sim; janela da troca de corpus |
| 7 | Avaliação camada 2 — rubrica e casos reais | Comitê pedagógico + registro de uso do piloto | não |
| 8 | Conferir `chunking.tamanho_maximo` contra corpus novo | Troca de corpus | — |

Os caminhos A1–A6 estão detalhados em
[recorte-de-conteudo-caminhos.md](recorte-de-conteudo-caminhos.md).

**Regra que organiza a coluna da direita:** toda mudança que invalida o índice
espera pela próxima reindexação obrigatória, e todas entram juntas. Reindexar
custa horas.

---

## Decisões pendentes

1. **Quando testar o tamanho de chunk.** É a maior distância entre o que fazemos
   (85 tokens) e a referência dos benchmarks (512), e o harness já mede — mas
   exige reindexar numa coleção paralela, o que são horas de GPU.
2. **Ligar o BM25 híbrido por padrão?** Ganha com idioma casado, perde sem. Como
   a mediação hoje traduz, o cenário é o favorável — mas medi antes do conserto
   da quantidade e o número precisa ser refeito.

---

## Invariantes — o que não pode quebrar

```bash
python3 -m unittest discover -s tests -t tests   # 216 testes, sem rede nem serviço
ruff check src/ tests/ main.py                   # lint
python3 main.py ambiente                         # serviços, modelos e artefatos
sha256sum data/chunks.jsonl                      # a991de28…  (69285 chunks)
```

1. **Nenhum módulo de `etapas/` importa outro de `etapas/`.**
2. **As etapas dependem de `protocolos.py`, nunca de `clientes/`.**

As duas são verificadas por `tests/test_estrutura.py`, que percorre os módulos
com `ast` — não dependem de ninguém lembrar delas. `marco.py`, `mediacao.py`,
`sessao.py` e `avaliacao.py` ficam na raiz do pacote pelo mesmo motivo de
`orquestrador.py`: compõem recuperação com geração, e isso não pertence a
nenhuma etapa.
