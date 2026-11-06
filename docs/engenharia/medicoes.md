# Medições

> [Índice dos documentos](../README.md) · [Roadmap](../roadmap.md) · [Arquitetura](arquitetura.md) · [Diretrizes](../diretrizes.md) §4

## Para que serve este documento

É o **caderno de medições** do projeto: cada número que justifica um padrão em vigor, os
experimentos que mudaram uma decisão, e os caminhos medidos e rejeitados. Quem quer saber *por
que* o sistema está configurado como está lê aqui; quem quer saber *o que* está pronto e o que
falta lê o [roadmap](../roadmap.md).

- **Cada seção leva a data e o comando que a reproduz.** Número sem isso é impressão
  ([diretrizes](../diretrizes.md) 4.1).
- **Não se reescreve medição antiga.** Quando um número é refeito, a remedição entra ao lado,
  datada, e a antiga fica — é o que permite ver quando algo mudou.
- Máquina das medições, salvo indicação: 16 GB de VRAM (RX 9070 XT), qwen2.5:7b Q4_K_M, bge-m3.
- Os números são sobre o **corpus descartável** (UESP) e um gabarito de 40 casos escrito pela
  equipe técnica. Servem para escolher entre alternativas, não para prometer desempenho no
  acervo do IPF.

---

## Um defeito do gabarito, corrigido em 2026-09-01

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

## Escolha da política de recuperação

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

**Sem reordenação, a melhor política é a quantidade dinâmica em α = 0,90.**
Recupera mais que o `k = 12` fixo (88% contra 85%) gastando menos trechos (10,3
contra 12), e adapta ao tipo de pergunta — menos fontes para dúvida factual, mais
para exploração.

**O padrão hoje é outro:** com a reordenação ligada (o padrão desde que ela entrou),
vale o `k = 8` fixo, e o `limiar_relativo` só atua com `--sem-reordenar` — o corte
por fração do topo pressupõe a lista ordenada por cosseno, e o cross-encoder ordena
por outro critério. `main.py config` marca o limiar como sem efeito nesse caso.

A partir de `k = 20` o orçamento de contexto começa a cortar, e em `k = 30`
corta em 15 dos 40 casos — ali o gargalo deixa de ser a recuperação e passa a
ser a janela.

### Por que relativo, e não por score absoluto

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

## Mediação — de −3 pontos a +2, depois de quatro correções

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

## Efeito do idioma da consulta

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

## Janela de contexto

`ollama ps` · `python3 main.py config`

| Medida | Valor | Como foi obtido |
|---|---|---|
| Janela em uso | **8192** tokens | `num_ctx` explícito; antes o Ollama usava 4096 sem avisar |
| Capacidade do qwen2.5:7b | 32768 tokens | `ollama show qwen2.5:7b` |
| Custo em VRAM de 4096 → 8192 | +0,4 GB (4,7 → 5,1) | `ollama ps` |
| Razão chars/token | **4,1** | `prompt_eval_count` em prompts reais (4,06 com k=3; 4,17 com k=8) |
| Prompt com marco genérico | k=3 → 1114 tok; k=8 → 2112 tok | idem |
| `/api/tokenize` no Ollama 0.33 | não existe (404) | por isso a estimativa é por caracteres |

## Corpus e índice

| Medida | Valor | Verificação |
|---|---|---|
| Páginas | 8896 arquivos, 8817 títulos distintos | `python3 main.py ambiente` |
| Chunks (padrão desde 2026-10-07) | 26808 · sha256 `47ed4084…` · `paragrafo_agrupado`, teto 2000 | `sha256sum data/chunks.jsonl` |
| Tamanho de chunk | mediana 1637 · p10 477 · p90 1996 · máx 2000 chars | passagem sobre o JSONL |
| Chunks anteriores (`paragrafo`) | 69285 · sha256 `a991de28…` · mediana 348 · em `data/chunks_paragrafo.jsonl`, coleção `uesp_lore` | mantidos para comparação |
| Truncamento no embedding | **descartado como risco** | bge-m3 via Ollama só ignora cauda acima de ~8k chars; zero chunks passam disso |

O truncamento silencioso estava marcado como risco em [fase 2](../plano/fase-2-prototipo.md) §7.
Está fechado para o corpus atual — mas a verificação é do par modelo+corpus, e
precisa ser refeita ao trocar qualquer um dos dois.

**Reindexar não custa mais horas.** Com o embedding na GPU, o corpus inteiro (38 M
caracteres) leva ~17 min sem limite e ~30–35 min em carga reduzida (fração 0,75). Medido ao
indexar as coleções abaixo.

## Extração do acervo — o limiar ainda não foi medido

`extracao.minimo_de_caracteres_por_pagina` = 50 (letras e dígitos) é **valor de partida**. Ele
decide que página vai ao OCR, e o certo depende dos PDFs do acervo, que ainda não chegaram. Errar
para cima custa tempo: página digital curta vai ao OCR, mas o resultado só substitui a camada
digital quando traz mais texto. Errar para baixo custa texto, porque uma página com camada de
lixo escapa do OCR.

Como medir quando os PDFs chegarem: rodar `main.py extrair` numa amostra por coleção, comparar
as páginas listadas em `paginas_ocr` e `paginas_abaixo_do_minimo` dos `.json` com o PDF aberto e
ajustar. Junto, cronometrar segundos por página de OCR, que ainda não têm número.

O que já foi conferido (2026-10-22, PDFs gerados com Ghostscript, no container
`podman build --target execucao`):

- OCRmyPDF 16.7 com Tesseract 5.5 e `por`: reconheceu sem erro a acentuação da página rasterizada
  a 300 dpi.
- O sidecar junta em **um pedaço só** as páginas puladas em sequência
  (`[OCR skipped on page(s) 2-3]`). Por isso a numeração é refeita pelos avisos
  (`clientes/pdf.paginas_do_sidecar`), não pela posição.
- O `pdftotext` do Poppler 26.01 fecha toda página com `\f`, a última inclusive.

**Página perdida por binarização (2026-10-23, P1 do [registro](../acervo/revisao-do-ocr.md)).**
No 7891/90109, datilografado em inglês sobre fundo cinza com faixa escura na borda, as páginas 2–12
saíram vazias. O defeito é do Tesseract, não do pipeline:

| Configuração | Caracteres por página (pp. 2–12) |
|---|---|
| Extração padrão (OCRmyPDF, binarização global) | 0 — o Tesseract registra "Too few characters. Skipping this page" |
| Tesseract direto, página a 300 dpi | 0 |
| OCRmyPDF com `--tesseract-thresholding sauvola`, `-l por` | 2.251–2.930 |
| idem, `-l eng` | 2.270–2.942 |

Com a binarização adaptativa (Sauvola) o texto volta, mas o começo das linhas ainda sai com
ruído. Reproduz com
`ocrmypdf -l eng --force-ocr --deskew --rotate-pages --tesseract-thresholding sauvola --pages 2-12 --sidecar s.txt --output-type none <pdf> -`.
Ainda não é padrão: falta medir contra transcrição de referência (CER), o que é a Fase 1 do plano
do [roadmap](../roadmap.md) §4, item 7.

## Motores de OCR — o Kraken lidera (2026-11-04)

Comparação de seis motores em 5 páginas do acervo, contra transcrições de referência **diplomáticas**
(mantêm os erros do original, os hífens de fim de linha e a falta de espaço depois da vírgula; ficam
fora carimbo, anotação a caneta, furos e marcas de gráfica). Feitas por Claude a partir da imagem e
conferidas uma a uma por Rener contra o papel. Ficam em `data/avaliacao_ocr/`, fora do git, porque
são texto integral do acervo.

Média por motor, cada página pesando igual:

| Motor | CER | WER | WER pont. separada | WER sem ordem | fora do dicionário | s/página |
|---|---|---|---|---|---|---|
| `atual` (OCRmyPDF, a extração de hoje) | 35,9% | 40,8% | 40,3% | 32,7% | 5,4% | 2,1 |
| `tesseract-otsu` | 28,3% | 32,7% | 32,0% | 31,0% | 4,0% | 0,8 |
| `tesseract-sauvola` | 14,7% | 25,5% | 23,5% | 20,9% | 7,5% | 1,1 |
| `tesseract-sauvola-unpaper` | 15,3% | 25,1% | 23,1% | 19,3% | 7,3% | 3,5 |
| `tesseract-otsu-reserva-sauvola` | 12,5% | 21,3% | 19,7% | 17,6% | 6,5% | 1,1 |
| `kraken-catmus` (CATMuS-Print Large, texto puro) | 7,1% | 17,3% | 12,4% | 17,2% | 5,7% | 14,6 |
| **`kraken-catmus-regioes`** (o mesmo, com as regras de região) | **1,4%** | **9,4%** | **4,0%** | **9,3%** | 5,4% | 14,7 |

CER por página dos três que importam:

| Página | O que testa | atual | otsu + reserva sauvola | kraken |
|---|---|---|---|---|
| 7891/90109 p. 3 | fundo cinza, margem cortada (P1) | 100% | 20,8% | **1,5%** |
| 7891/90108 p. 2 | fotografada, linhas curvas, inglês | 37,1% | 9,7% | **0,4%** |
| 7891/1133 p. 4 | linhas embaralhadas (P11) | 25,2% | **14,7%** | 15,6% |
| 7891/1133 p. 2 | datiloscrito limpo | 10,0% | 10,1% | 10,5% |
| 7891/1129 p. 2 | impresso, com carimbo | 7,3% | 7,2% | 7,9% |

O que os números dizem:

- **O Kraken ganha onde o Tesseract quebra**, em página degradada ou fotografada, por causa da
  segmentação por linha de base. Nas páginas limpas empata no CER.
- **O WER comum castiga o Kraken por convenção, não por leitura.** Ele põe espaço depois da vírgula
  e o datiloscrito não, o que conta como duas palavras erradas. Com a pontuação separada, o Kraken
  vai de 17,3% para 12,4%. O que resta contra ele nas páginas datilografadas são as linhas de ruído
  dos furos de encadernação: até 33 numa página, cada uma uma letra solta. A normalização pendente
  (roadmap §4, item 9) cuida disso.
- **Sauvola só serve de reserva.** Sozinho resgata a página de fundo cinza, mas piora a página
  inclinada (14,7% → 25,1%). A combinação "Otsu, e Sauvola quando a página sai quase vazia" pega o
  melhor dos dois, com um critério que não depende da referência.
- **A fração fora do dicionário não acompanha o CER.** O caminho atual erra 35,9% dos caracteres e
  tem só 5,4% de palavras desconhecidas: página vazia não tem palavra para estar errada, e texto
  fora de ordem é feito de palavras certas. Ela não serve sozinha como nota de qualidade da página
  (roadmap §4, item 7): precisa ao menos da densidade de caracteres e de um sinal de ordem.
- **A confiança por palavra do Kraken vê hesitação, não acerto.** Na 7891/1133 p. 2 (saída ALTO, 465
  palavras, mediana 1,0), as 20 palavras de confiança mais baixa (0,13–0,52) são todas ruído dos
  furos, e as letras cobertas por caneta ficam um pouco abaixo da mediana (0,93 e 0,95). Mas os
  acentos perdidos saem com 0,996–1,0: é viés do modelo, que viu pouco português acentuado, não
  dúvida de leitura. Esses o dicionário pega (`circulos`, `opinioes` não existem). A nota de
  qualidade soma os dois sinais palavra a palavra; nenhum basta sozinho, e nenhum pega acento
  perdido que forma outra palavra válida. O ALTO sai da mesma execução, com `-a` no lugar do texto.
- **O tempo do Kraken é reconhecimento em CPU, não partida de container.** Na extração, com as 4
  páginas do 7891/1133 numa execução só, foram 49 s, ~12 s por página contra 14,6 s uma a uma: a
  partida e a carga do modelo custam ~3 s. As 238 páginas que a extração atual manda ao OCR levariam
  ~48 min. A GPU (ROCm) é o que reduziria isso, e fica para quando o volume pedir.

**Regiões com tipo (2026-11-04).** `kraken-catmus-regioes` é o texto que a extração grava: o PAGE
XML do Kraken com as regras de região aplicadas (carimbo, furos, número de página). Ele leva o
Kraken de 7,1% para **1,4%** de CER. O ganho é quase todo das páginas datilografadas do 7891/1133 e
do 7891/1129, onde o ruído dos furos e o carimbo eram o grosso do erro (p. 2: 10,5% → 1,8%; p. 4,
a do P11: 15,6% → 1,9%). Nas páginas sem furo nem carimbo o número não muda, e em nenhuma página
subiu: nesta amostra a regra não apagou texto legítimo.

O segmentador ora separa os furos numa região estreita da margem, ora os deixa **dentro** da região
do corpo (no 7891/1133, p. 2 de um jeito, pp. 1, 3 e 4 do outro). Só a regra por região deixava
3,3% na p. 4; a regra por linha, que tira o fragmento encostado na margem, levou a 1,9%. As
anotações a caneta do alto da p. 1 também são fragmentos, mas ficam no meio da página e não são
tocadas: são o P7, decisão de revisão. O PAGE regravado sem glifos tem 241 KB por página, contra
830 KB do que o Kraken escreve. Reproduz com `python3 main.py avaliar-ocr --gerar kraken-catmus-regioes`.

O texto extraído hoje (Tesseract) tem, em duas páginas, a linha do e-mail do carimbo **colada** ao
começo do texto (`…paulofreire.orgO Encontro`). Linha assim não se parece com o carimbo nem com o
texto, e a regra não a separa. Se o Kraken também juntar as duas, é o caso que justifica mascarar
o carimbo na imagem antes do OCR.

**Dispensada:** a sexta página, 7891/1134 p. 1 (P6: colunas e legenda, em espanhol). O P6 é
problema de região, que se conserta desenhando no eScriptorium, não trocando de motor. Cinco páginas são amostra pequena: a medição confirma a
direção (Kraken como motor-alvo), não um número para o acervo.

Reproduz com `python3 main.py avaliar-ocr --gerar todos`, com o container `rag-kraken` construído e
o modelo baixado (ver README). Sem `--gerar`, só recompara os candidatos já gravados.

## Normalização e relatório de qualidade (2026-11-06)

### O acervo inteiro com o Kraken

Os 39 PDFs (296 páginas) foram reextraídos com o Kraken: 253 páginas por OCR e 43 de texto
original (só o 7891/90147, diagramado no InDesign). Nenhum PDF perdeu página: o número de `\f`
bate com o de páginas em todos.

Só **1 página ficou abaixo do mínimo**, contra 20 na extração do Tesseract. As 11 páginas cinzas
do 7891/90109 voltaram. A que sobrou, 7891/25 p. 1, é uma capa: título em letra grande sobre um
desenho, que o segmentador não pegou.

O texto anterior foi guardado em `data/texto_acervo_tesseract/` para a comparação.
Comando: `python3 main.py extrair --refazer`, ~50 min na CPU.

**Texto pronto contra OCR anterior.** A página é escaneada quando uma imagem cobre pelo menos 90%
dela (`pdfimages -list`). No acervo:

| PDFs | Cobertura das páginas |
|---|---|
| todos os escaneados | 100% ou mais (a imagem passa da margem) |
| o diagramado (7891/90147) | no máximo 22% (uma foto) |

O 7891/4657 traz um OCR do Acrobat 9 sobre a imagem. Naquele francês, o Kraken troca `a` por `o` e
`d` (`éducotion`, `serdit`), e o Acrobat erra menos. Fica a leitura com menor fração fora do
dicionário:

| Página | Acrobat | Kraken | Fica |
|---|---|---|---|
| 1 | 8,2% | 7,9% | Kraken (tira também o carimbo) |
| 2 | 5,2% | 14,0% | Acrobat |
| 3 | 5,8% | 13,0% | Acrobat |
| 4 | 6,0% | 13,4% | Acrobat |

### Normalização: medida contra a referência

`python3 main.py avaliar-ocr --normalizado` aplica as mesmas regras à referência e ao candidato.
Quebra de linha e hífen de fim de linha não são conteúdo.

| Motor | CER | WER | WER pont. separada |
|---|---|---|---|
| `kraken-catmus-regioes` bruto | 1,4% | 9,4% | 4,0% |
| `kraken-catmus-regioes` normalizado | **1,0%** | **4,7%** | 4,2% |

Nenhuma página piora no CER. O maior ganho é no 7891/1133 p. 2, onde o WER vai de 19,0% para 3,7%
pelas palavras partidas e pela pontuação colada. No 7891/90109 p. 3 o WER passa de 8,0% para 8,1%.

**Auditoria das regras.** Foram 30 exemplos sorteados de cada regra no acervo, lidos um a um.

| Regra | Aplicações | Acertos na amostra | Erros achados, e o ajuste feito |
|---|---|---|---|
| hífen marcado (`¬`) | 1625 | 27 de 30 | O CATMuS marca também o hífen que fica (`tornando¬` / `se`). Com dicionário, as duas metades existindo e a junta não, o hífen fica |
| hífen comum | 106 | 30 de 30 | — |
| hífen mantido | 285 | quase todos em espanhol, sem dicionário | Em português, mantém certo `assumi-los` e `verifica-se` |
| sem hífen | 128 | 24 de 30 | Pedaços curtos (`vel` / `e` → `vele`, `o` / `va` → `ova`). Passou a exigir junta de 5 letras ou mais (`minimo_da_junta_sem_hifen`) |
| pontuação colada | 49 | 27 de 30 | `Ph.D.` e o código `FPF.OPF` eram abertos. Passou a exigir minúscula antes, e a não abrir abreviação |

As contagens são as do texto já com os ajustes e antes dos dicionários de espanhol e francês. Com
eles, o hífen comum sobe para 159 junções e o mantido cai para 260. O CER normalizado ficou o mesmo
depois dos ajustes.

### O relatório: níveis do acervo e o que eles valem

Comando: `python3 main.py normalizar && python3 main.py relatorio-ocr`. A planilha fica em
`data/relatorios/`.

Os níveis vêm da fração das palavras de inicial minúscula fora do dicionário:

| Nível | Fração fora do dicionário |
|---|---|
| bom | até 3% |
| regular | até 10% |
| ruim | acima de 10%, ou página vazia |

Mais de 10% de palavras hesitantes (confiança abaixo de 0,5) baixa um nível. Com os dicionários de
português, inglês, espanhol e francês:

| | Bom | Regular | Ruim | Sem medida | Texto original |
|---|---|---|---|---|---|
| Documentos (39) | 11 | 22 | 5 | 0 | 1 |
| Páginas (296) | 87 | 117 | 45 | 4 | 43 |

Por idioma, em documentos:

| Idioma | Bom | Regular | Ruim | Texto original |
|---|---|---|---|---|
| português (21, dois deles detectados) | 5 | 11 | 4 | 1 |
| inglês (9) | 3 | 6 | — | — |
| espanhol (5) | 1 | 3 | 1 | — |
| francês (4) | 2 | 2 | — | — |

Ficam boas ou são texto original 130 das 296 páginas (44%).

Os problemas detectados, em número de documentos:

| Problema | Documentos |
|---|---|
| P2, acento perdido ou muitas palavras fora do dicionário | 39 |
| P7, linhas de baixa confiança | 12 |
| P6, colunas | 10 |
| P3, idioma suspeito | 2 |

**Os dois P3 procedem:**
- o 7891/3011 está catalogado como espanhol e o texto é português: é a primeira ocorrência de
  metadado divergente. A medida dele sai distorcida, porque foi feita com o dicionário de espanhol;
- o 7891/90147 é bilíngue, com textos em português e em espanhol, e não tem idioma no catálogo.

**Conferência por amostra.** Seis páginas sorteadas, duas por nível, comparando imagem e texto
normalizado:

- **cinco coerentes**:
  - as boas leem bem, com acentos perdidos esparsos;
  - as regulares são legíveis com erro frequente (`uvo`, `roçq`, `escolos comunitúrios`);
  - a ruim do 7891/1135 p. 1 é capa de revista, que virou lixo;
- **o desvio**: o 7891/4398 p. 1 é "ruim" com o corpo legível. Metade da página é tabela de números
  e gráfico, e o lixo deles pesa na fração. O nível é da página inteira, e tabela ainda não é
  região separada.

**A régua do dicionário não serve para comparar motores.**
- Nas 5 páginas de referência, a fração fora do dicionário é igual para o Tesseract e para o
  Kraken (5,4%), com CER de 35,9% contra 1,4%. A fração não vê página perdida nem linha que falta.
- No acervo ela pune o acento que o CATMuS perde e o Tesseract, com o modelo de português, não
  perde. Por isso a média fica em 7,3% para o Kraken contra 3,9% para o Tesseract.

Ela serve para ordenar as páginas de um mesmo motor, que é o uso no relatório. Na escolha entre o
OCR anterior e o Kraken numa mesma página, a régua tem o mesmo viés, que só pesa contra o Kraken.

**Onde o Kraken perde de fato.** Na comparação página a página (as 253 do Kraken, com folga de 5
pontos, antes dos dicionários de espanhol e francês), há empate em 130. O Tesseract ganha em 22 e
o Kraken em 3; em 11 o Tesseract deixou a página vazia, e 87 ficaram sem medida (espanhol e
francês). Com os quatro dicionários, a média fora do dicionário nos 38 documentos medidos é 7,7%
para o Kraken e 5,4% para o Tesseract.

Os trechos confirmam dois casos:

- **inglês**: o CATMuS troca `w` por `v` (`ve`, `avaiting`, 7891/1108);
- **fotocópia degradada de datiloscrito**: "Ecte testo tem a mientdo de provocat" (7891/3316).

**Decisão (2026-11-06): fica só o Kraken.** A escolha por página entre os dois motores foi
oferecida e recusada. A correção é treinar o Kraken no acervo com páginas revisadas no
eScriptorium, a começar por inglês e cópias degradadas (roadmap §4, item 7, fase 7).

## Tamanho do recorte — agrupado de 2000 vence (2026-10-05)

`paragrafo_agrupado` junta parágrafos consecutivos até o teto, em vez de descartar
os curtos. Três coleções, mesmo gabarito, mesma configuração (carga reduzida, fração 0,75, no
container com GPU para o reordenador):

```bash
python3 main.py --chunks chunks_agrupado_2000.jsonl chunking --estrategia paragrafo_agrupado --tamanho-maximo 2000
python3 main.py --carga reduzida --chunks chunks_agrupado_2000.jsonl --colecao uesp_lore_agrupado_2000 indexar
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

## Memória de conversa — o seguimento entendido (2026-10-07)

Antes, cada pergunta do modo conversa chegava sozinha: "e os Khajiit?" ia à busca
como "e os Khajiit?". Agora, com histórico, uma chamada ao modelo reescreve o
seguimento como pergunta autônoma antes da busca, e as últimas trocas entram no
prompt da resposta. Desenho em [arquitetura](arquitetura.md) §4.2.

`python3 main.py avaliar --conversa` · 16 casos de `avaliacao/casos_conversa.jsonl` ·
mediação + reordenação, `k = 8` · duas rodadas

| O que vai à busca | recall | cobertura | MRR | cortes |
|---|---|---|---|---|
| Seguimento cru | 62% | 50–56% | 0,44–0,45 | 0/16 |
| **Seguimento reescrito** | **94%** | **81–84%** | **0,61–0,62** | 0/16 |

- **+31 pontos de recall**, estável nas duas rodadas. Os casos que mais ganham são
  os que o cru não achava de jeito nenhum: "o que aconteceu com eles?" → "o que
  aconteceu com os Falmer?", e "qual a diferença entre os dois?" → "qual a
  diferença entre os Altmer e os Bosmer?".
- **Contaminação: zero em 4.** Os quatro casos de troca de assunto ("o que é o
  Thalmor?" depois dos argonianos) foram à busca intactos, nas duas rodadas.
- **Uma piora, e não da reescrita:** "o que ele fez em Red Mountain?" virou
  corretamente "o que Kagrenac fez em Red Mountain?", e mesmo assim a página caiu
  do 2º para o 4º lugar numa rodada e sumiu do top-8 na outra. A reescrita estava
  certa; quem oscilou foi a busca. Cobertura e MRR variam entre rodadas pelo mesmo
  motivo — cada caso vale 6,25 pontos aqui.
- **Custo:** uma chamada ao modelo por seguimento, ~0,5–1 s com o modelo já
  carregado. Sem histórico, nenhuma.

**Força da evidência:** 16 casos, escritos pela equipe técnica sem olhar o que o
buscador devolve. O ganho é grande demais para ser ruído, mas o gabarito é pequeno e
descartável. A geração com histórico (o "explique o ponto 2") **não é medida** —
é rubrica humana, como toda qualidade de resposta.

## Limitador de carga — poupar o hardware de dentro do app (2026-10-05)

**Exposto como dois modos desde 2026-10-07:** `--carga total` (padrão, o
comportamento original) e `--carga reduzida` (**experimental**, por causa do efeito
"em aberto" abaixo). O reduzido fixa fração 0,75, lote 8 e 2 threads de CPU no
Ollama (`carga.MODOS_DE_CARGA`). As medições desta seção são anteriores a isso: foram
feitas com a fração configurável, e as indexações longas em 0,75 e lote 8 **com as
threads do Ollama no padrão**.

Depois de cada lote o pipeline descansa `duração × (1/F − 1)`, num limitador só
para o processo inteiro (embutidor, reordenador e gerador de apoio). Medido na RX 9070 XT lendo `freq1_input`,
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
O modo reduzido manda `num_thread = 2` em cada requisição:

| `num_thread` | vazão | CPU do Ollama |
|---|---|---|
| padrão | 30,6k ch/s | 419% de um núcleo |
| 2 | 30,7k ch/s | 149% |

Mesma vazão, um terço da CPU. Fica em 0 (padrão do Ollama) até ser medido na
geração; mudar o valor faz o Ollama recarregar o modelo uma vez.

**Em aberto — picos na indexação longa.** Nas duas indexações reais com
fração 0,75 — hoje, o modo reduzido — (64 min no total), o limitador cumpriu a proporção (descanso de
25% do tempo nas duas), mas a placa ficou em ~80 W só nos primeiros ~25 min; de
17:28 em diante passou a 200–250 W e junção de 82–88 °C, por 40 min seguidos.
Não reproduziu em 150 s do mesmo caminho de código (80 W, 51–59 °C), nem havia
outro processo na GPU (`rocm-smi --showpids`). Hipóteses não testadas: efeito que
só aparece com o tempo (temperatura acumulada mudando a política do governador),
ou trechos do corpus que mudam a duração dos lotes. **Até isso ser entendido, o
limitador não deve ser tratado como garantia de potência em execução longa.**
Para investigar: indexar de novo com o monitor de sysfs e registrar a duração de
cada lote junto com o horário.

## Limiar de redundância da mediação

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

## BM25 híbrido — depende do idioma, e o peso do RRF decide

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
