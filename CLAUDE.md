# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## O que é este repositório

Protótipo da **Fase 2** do projeto IA Freiriana (Instituto Paulo Freire): um pipeline RAG local
completo — download de corpus → chunking → embedding/indexação → recuperação → geração.

**Onde o desenvolvimento está:** `@docs/estado-do-desenvolvimento.md` — o que está pronto, o que é
provisório, o que falta e as medições em vigor. É o primeiro doc a ler, e o que atualizar quando
alguma dessas coisas mudar.

O plano por fases está em `docs/`. Leia sob demanda, não preventivamente:
`@docs/00-plano-geral-implementacao.md`

**O corpus UESP é descartável.** `data/corpus_uesp/` (lore de Elder Scrolls) existe só para
exercitar o pipeline com volume real enquanto o acervo do Centro de Referência Paulo Freire não
está pronto (Fase 1). Ao trocar para o corpus real, muda a coleção (`uesp_lore` → `corpus_ipf`) e
o módulo de download — não a arquitetura. Não trate a lore como domínio do projeto.

## Idioma do código

**Todo o código é escrito em português brasileiro** — nomes de função, variáveis, campos de
dataclass, docstrings, comentários e saída de `print`. Isso é deliberado e 100% consistente.
Ao escrever ou editar código aqui, mantenha pt-BR (`buscar`, `montar_prompt`, `NOME_COLECAO`,
`titulo_pagina`), nunca inglês.

As mensagens ao usuário nesta conversa também em português.

## Ponto de entrada único

Tudo passa por `main.py` — menu interativo sem argumento, subcomandos para automação. As duas
formas chamam as mesmas funções em `src/rag/interface/acoes.py`, então **não existe
funcionalidade que só o menu ou só a CLI alcance**. Ao adicionar uma capacidade, adicione a ação
lá e ligue nas duas portas.

```bash
python3 main.py                    # menu
python3 main.py ambiente           # diagnóstico (use antes de investigar qualquer falha)
python3 main.py chunking           # --saida OUTRO.jsonl para não destruir o chunks.jsonl indexado
python3 main.py indexar            # retoma de onde parou; --recriar para refazer
python3 main.py --carga 0.75 indexar   # poupa o hardware: descansa 25% do tempo, por lote
python3 main.py --chunks X.jsonl --colecao X indexar   # experimento sem tocar no índice padrão
python3 main.py buscar "..."       # só recuperação; --sem-intermediar desliga a mediação
python3 main.py perguntar "..."    # ciclo RAG completo; --direto pula a problematização
python3 main.py avaliar --comparar # recall@k com e sem mediação (não gera texto)
python3 main.py acelerador         # qual torch esta máquina precisa (para o build)
python3 main.py marcos             # marcos pedagógicos disponíveis
python3 main.py config             # configuração em vigor, com a origem de cada valor
```

Rode a partir da raiz do repositório. Os caminhos são resolvidos a partir de
`config.RAIZ_PROJETO`, então o diretório atual não quebra nada, mas os comandos documentados
assumem a raiz.

## Arquitetura — o que não pode ser quebrado

```
main.py              fino: só ajusta sys.path e delega
config.toml          sobreposição de configuração desta máquina (gitignored)
marcos/*.md          marcos pedagógicos — versionados, editáveis por quem não programa
src/rag/
  config.py          parâmetros de todas as etapas + leitura/escrita do config.toml
  protocolos.py      contratos (Embutidor, Gerador, RepositorioVetorial, MarcoPedagogico...)
  orquestrador.py    MotorRag — o ciclo recuperação + geração
  marco.py           carrega e valida os marcos
  mediacao.py        IntermediadorDeConsulta — reformula, decompõe e funde (RRF)
  sessao.py          Dialogo — a máquina de estados que problematiza antes de responder
  avaliacao.py       recall@k contra o gabarito de avaliacao/casos.jsonl
  acelerador.py      detecta GPU e diz qual build de torch instalar
  lexico.py          BM25 e a fusão dele com a busca densa (desligado por padrão)
  carga.py           limitador de carga: embrulha embutidor, reordenador e gerador de apoio
  servico.py         onde as implementações concretas encontram os protocolos
  clientes/          Ollama, Qdrant, UESP, sessão HTTP com repetição
  etapas/            download, chunking, indexacao, recuperacao, geracao
  interface/         console, menu, cli, acoes
```

`marco.py`, `mediacao.py`, `sessao.py` e `avaliacao.py` ficam na raiz do pacote, **nunca em
`etapas/`**, pelo mesmo motivo de `orquestrador.py`: cada um compõe recuperação com geração, e pôr
qualquer um deles em `etapas/` obrigaria uma etapa a importar outra. As três camadas se empilham sem que
nenhuma conheça as outras:

```
pergunta → Dialogo (triagem, problematização) → consulta consolidada
         → IntermediadorDeConsulta (reformula, decompõe, funde) → N buscas
         → MotorRag + marco → resposta
```

Duas regras estruturais, ambas verificáveis:

1. **Nenhum módulo em `etapas/` importa outro módulo de `etapas/`.** Elas se comunicam por
   artefato em disco. É o que permite refazer uma etapa sem afetar as outras.
2. **As etapas dependem de `protocolos.py`, não de `clientes/`.** Trocar o banco vetorial é
   escrever outra classe com os mesmos métodos e mudar uma linha em `servico.py`. Os testes
   dependem disso: rodam com dublês, sem Qdrant nem Ollama.

**As duas são testadas** — `tests/test_estrutura.py` percorre `etapas/` com `ast` e falha se
algum import quebrar qualquer uma. Não é mais disciplina, é a suíte. Se precisar quebrá-las, é
sinal de que o código pertence a `orquestrador.py`, a um módulo de composição na raiz, ou a
`clientes/` — não à etapa.

## Pipeline — a ordem importa

Cada etapa consome a saída da anterior:

```
download    → data/corpus_uesp/*.txt   (~9k páginas, demorado)
chunking    → data/chunks.jsonl
indexacao   → coleção uesp_lore no Qdrant   (~17 min na GPU; ~35 com --carga 0.75)
recuperacao → trechos
geracao     → resposta
```

`buscar` isola a camada de recuperação de propósito: recall@k é avaliável sem gerar texto.
Ao depurar qualidade de resposta, verifique a recuperação com ele antes de mexer no prompt.

## Serviços — precisam estar de pé

```
podman compose up -d      # Qdrant em localhost:6333 (painel: /dashboard)
ollama pull bge-m3        # embedding, 1024 dimensões
ollama pull qwen2.5:7b    # geração
```

Use **podman**, não docker. Nesta máquina `docker` no PATH já é o shim do podman, e o podman roda
rootless — os volumes usam a flag `:Z` do SELinux por causa disso.

O `compose.yaml` também roda a aplicação em container. **O Ollama fica no host** — a GPU dele já
está configurada, e containerizá-lo custaria a imagem ROCm mais o re-download dos modelos:

```bash
podman compose --profile execucao build rag && podman compose run --rm rag ambiente
podman compose --profile gpu run --rm rag-gpu           # com reordenação
```

Três coisas que não são óbvias e custaram builds inteiros para descobrir:

- **Os serviços `rag` usam rede do host.** O Ollama escuta em `127.0.0.1`, e com rede própria o
  container não o enxergaria — seria preciso alterar o serviço do host. Compartilhando a rede,
  a configuração padrão do código já serve e nada muda fora do repositório.
- **O ROCm precisa de `/dev/dri` inteiro**, não só do `renderD*`, mais `keep-groups`. Sem isso
  reporta zero GPUs mesmo com os dispositivos presentes.
- **Nada de pesado depois do código no `Containerfile`.** `COPY src/`, `ENTRYPOINT` e `CMD` ficam
  no fim de cada estágio; postos antes do `pip install torch`, faziam uma edição de uma linha
  custar 6 GB de download.

O código do host é montado no container (`./src:/app/src`), então editar não exige reconstruir.
A contrapartida é que a imagem publicável fica defasada até o próximo build.

`python3 main.py ambiente` diagnostica os dois serviços, os modelos, a dimensão da coleção e os
artefatos de cada etapa. É o primeiro comando a rodar diante de qualquer erro.

## Marco pedagógico

O marco é **dado versionado carregado em tempo de execução, nunca prompt no código**
(`docs/fase-0-desenho-e-contratos.md` §3.5). Vive em `marcos/*.md`, em Markdown com frontmatter,
e é editável por quem não programa — `marcos/LEIA-ME.md` é a instrução para o comitê.

- `generico` é o ativo por padrão: serve ao corpus descartável e não tem valor pedagógico.
- `freiriano` é **esqueleto**, `versao: 0`. A redação é do comitê pedagógico, não de
  programadores (`docs/fase-2-prototipo.md` §4.6). **Não escreva o conteúdo dele.** Se faltar
  alguma seção estrutural, acrescente a seção com a pergunta que ela precisa responder.
- Três seções alimentam camadas diferentes: `Decomposição` orienta a mediação, `Triagem` e
  `Problematização` orientam a sessão. As demais entram no prompt da resposta, e uma seção nova
  criada pelo comitê entra sozinha, sem alteração de código.
- Marco quebrado **levanta erro**; não cai no prompt genérico em silêncio. Isso é deliberado.

## Armadilhas

- **`montar_prompt()` em `etapas/geracao.py` é o caminho sem marco**, usado só quando
  `marco.ativo` está vazio. O caminho normal é `montador_do_marco()`. Não "melhore" o texto
  genérico dali: comportamento se ajusta editando `marcos/*.md`, que é o ponto todo.
- **A avaliação mede recuperação, não geração — e isso é deliberado.** `docs/fase-3` §7 separa as
  duas porque "recuperação ruim e geração ruim têm correções opostas". A qualidade da resposta é
  rubrica humana (§5), e LLM como juiz premia o "freirês" que deveria pegar (§8). Não acrescente
  métrica automática de qualidade textual a `avaliacao.py`.
- **`recall@k` não é o que chega ao modelo — confira os dois.** O harness mede recuperação sem
  gerar texto; o orçamento de contexto pode descartar trechos depois. Conferido: em `k = 8`,
  `k = 12` e nas políticas dinâmicas, zero dos 40 casos sofrem corte, então os números batem. Em
  `k = 20`, dois casos são cortados. Ao mexer em `k`, em `num_ctx` ou no tamanho do marco, refaça
  essa conferência — está descrita em `docs/estado-do-desenvolvimento.md`.
- **O gabarito de `avaliacao/casos.jsonl` mede o avaliador junto com o sistema.** Já houve um
  defeito real: as páginas esperadas foram escritas do modelo mental do domínio, ignorando as
  páginas-índice do acervo (`Lore:Races`, `Lore:Religions`), e seis casos cobravam a página
  errada — o recall aparecia 5 pontos abaixo do real. Ao acrescentar caso, confira o título
  contra o índice **e** se é mesmo a melhor página para aquela pergunta. E nunca ajuste o
  gabarito para o que o buscador devolveu: isso transforma a métrica em espelho.
- **A folga do prompt é do marco, não dos trechos.** O `generico` tem 975 caracteres; em `k = 8`
  cabem ~13.500 antes de custar trecho recuperado, e em `k = 20` cabem ~1.600. É a razão mais
  concreta para `k` não ser maior, e ela não aparece em métrica de recuperação nenhuma.
- **Corte por score absoluto não funciona neste corpus, e `score_minimo` fica em 0 por isso.**
  Trecho relevante e irrelevante têm a mesma faixa de score (medianas 0,552 e 0,551), e valores
  altos o bastante para filtrar deixam perguntas sem resultado nenhum (dez de quarenta em 0,60).
  A alternativa que funciona é `busca.limiar_relativo`, relativo ao topo de cada pergunta —
  desligada por padrão, medida em `docs/estado-do-desenvolvimento.md`.
- **A mediação decompõe pergunta composta, e só isso.** Empata em recall com a busca direta e
  ganha 1 ponto de cobertura, a ~9× o tempo. Traduzir para o idioma do acervo é capacidade
  existente (`idioma_do_acervo` no frontmatter do marco), hoje sem nenhum marco que a declare.
  Antes de ajustar parâmetro dela, rode `main.py avaliar --comparar`.
- **Reordenação e corte relativo não se misturam.** O corte por fração do topo pressupõe a lista
  ordenada por cosseno; o cross-encoder ordena por outro critério, e o primeiro colocado pode ter
  similaridade menor que o terceiro — a busca chegou a devolver 21 trechos com teto de 20. Com
  reordenação vale o `k` fixo, e a decisão mora em `decidir_quantidade`, **uma função só** usada
  pela busca direta e pela mediação. Estavam duplicadas, e um conserto valeu só num dos lados.
- **O reordenador roda uma vez, sobre a lista fundida — nunca por sub-consulta.** Reordenar por
  sub-consulta multiplicaria o custo e julgaria contra a sub-consulta em vez de contra a pergunta
  original. Por isso `servico.py` dá o reordenador à mediação quando ela está ligada, e ao
  `Recuperador` quando não está — nunca aos dois.
- **`torch` tem builds incompatíveis por acelerador**, e o errado instala em silêncio e cai para
  CPU. `main.py acelerador --indice` diz qual esta máquina precisa; o `Containerfile` recebe por
  `--build-arg` e **falha o build** se o acelerador pedido não aparecer.
- **BM25 híbrido (`rag/lexico.py`) depende do idioma e do peso do RRF.** Sem tradução ele piora
  (88% denso contra 85% híbrido); com a mediação traduzindo, melhora (90% contra 92%). `peso_denso`
  precisa ser ≥2 — com voto igual o esparso arrasta o denso para baixo. E **os scores léxicos são
  reescalados para a faixa do denso**: cosseno fica em ~0,6 e BM25 passa de 10, e a política de
  quantidade dinâmica corta por fração do topo. Desligado por padrão.
- **Não suba `intermediacao.limiar_de_redundancia` sem refazer a medição.** As faixas de cosseno
  de consultas redundantes e distintas se sobrepõem (0,620–0,988 contra 0,664–0,893), então o
  limiar alto é escolha informada, não descuido. Quem reduz o número de sub-consultas é o prompt.
- **`num_ctx` precisa ser explícito.** Sem ele o Ollama usa 4096 e trunca o prompt em silêncio,
  mesmo com o modelo aceitando 32768. O orçamento de trechos sai de `num_ctx - reserva_para_resposta`
  e é aplicado no `MotorRag`, não no montador — a lista devolvida à interface tem de ser a mesma
  que foi ao modelo, senão `validar_citacoes` aprova fonte que o modelo nunca viu.
- **A mediação custa uma chamada ao modelo por pergunta.** `IntermediadorDeConsulta` reformula e
  decompõe antes de embutir. Para medir `recall@k` sem esse custo — e para comparar contra a
  linha de base — use `buscar --sem-intermediar`. Qualquer tropeço dela (modelo fora do ar, saída
  ilegível) vira busca direta, nunca exceção: a recuperação tem de continuar avaliável sozinha.
- **A sessão dialógica só roda com terminal.** `cli._escolher_modo_de_pergunta` desliga a
  problematização quando `sys.stdin.isatty()` é falso, porque as perguntas devolvidas não teriam
  para quem ir e o processo ficaria pendurado num `input()`. É isso que mantém
  `main.py perguntar "..."` funcionando em cron, pipe e script. Não remova essa guarda.
- **As flags globais usam `default=argparse.SUPPRESS`.** Sem isso, o subparser parseia num
  namespace novo e copia por cima, e `main.py --colecao x buscar ...` perde a flag sem erro
  nenhum. E **não use `parser.set_defaults`** para elas: ele reescreve o `default` do objeto da
  ação, que `parents` compartilha, desfazendo o SUPPRESS. Normalizar depois do parse é o
  contrapeso (`_normalizar_globais`). Coberto por teste.
- **`config.toml` é sobreposição, não substituição.** A precedência é padrões de `config.py` →
  arquivo → flags, e o arquivo guarda só o que difere do padrão. Gravar só acontece quando pedido
  (`config --salvar`), e regrava o arquivo perdendo comentários do usuário. `config.exemplo.toml`
  é **gerado** das dataclasses: depois de acrescentar um campo, rode
  `python3 -c "import sys; sys.path.insert(0,'src'); from rag.config import escrever_exemplo; escrever_exemplo()"`
  — há teste que falha se ele ficar defasado.
- **`Chunk.como_dicionario()` omite campo em branco.** Os campos de proveniência (`pagina`,
  `secao`, `inicio`, `fim`, `versao_embedding`, `restricao_uso`) foram acrescentados de forma
  aditiva, e é essa omissão que mantém o `chunks.jsonl` byte a byte idêntico e o índice válido.
  Gravar campo vazio custaria uma reindexação de horas.
- **`main.py chunking` sobrescreve `data/chunks.jsonl`**, que é o arquivo correspondente aos
  pontos indexados. Para experimentar estratégia, use `--saida OUTRO.jsonl` e indexe contra
  `--colecao OUTRA`.
- **Mudar a estratégia de chunking invalida o índice inteiro.** A saída de `chunking` com a
  estratégia padrão (`paragrafo`) é byte a byte igual à do protótipo original — 69285 chunks,
  sha256 `a991de28...`. `paragrafo_agrupado` existe e é melhor (não descarta parágrafo curto),
  mas trocar exige reindexar tudo. Não troque de passagem — o agrupado de 2000 já está
  medido (melhor) e indexado em `uesp_lore_agrupado_2000`, esperando decisão de promoção. **Regra que sai
  disso: toda mudança que invalida o índice espera pela próxima reindexação obrigatória, e todas
  entram juntas** — os caminhos e a ordem estão em `docs/recorte-de-conteudo-caminhos.md`.
- **`DIMENSAO_VETOR` tem que bater com a saída do modelo de embedding.** Isso agora é
  *verificado antes* de qualquer processamento (`garantir_colecao`), com erro explicado — não é
  mais o modo de falha silencioso que era. Ao trocar o modelo, use `indexar --recriar`.
- **A indexação retoma por padrão.** Chunks já indexados são pulados (consulta por `uuid5` do
  `chunk_id`), então repetir a etapa custa segundos em vez de horas. `--sem-retomada` desliga.
- **O limitador de carga descansa por lote, e curto de propósito.** Rajada de segundos
  com pausa de segundos dá a mesma média com a placa oscilando 48↔77 °C — ciclo térmico,
  o estresse que se quer evitar. Teto de vazão (estilo FPS) também foi medido e rejeitado:
  briga com o governador da GPU. E o limitador é **um só por processo**, segurando lock
  durante a pausa; pausa por thread não limita nada com 4 workers. Números em
  `docs/estado-do-desenvolvimento.md`. Há um efeito em aberto (picos em execução longa).
- **Quem esquenta a CPU no embedding é o `llama-server`, não o app** — ~4 núcleos em
  espera ativa pela GPU. `carga.threads_de_cpu = 2` corta para ~1,5 núcleo sem perder
  vazão (medido no embedding; na geração, não).
- **Os padrões ficam em `src/rag/config.py`**, não espalhados pelos módulos e não em `.env`. Por
  cima deles entra o `config.toml` (opcional, gitignored), e por cima dele as flags e o menu.
  Ajuste de menu e de flag vale só para aquela execução até ser gravado com `config --salvar`.

## Testes

```bash
python3 -m unittest discover -s tests -t tests
```

313 testes, sem dependência de serviço externo ou rede. Ao mexer em chunking, indexação ou no
ciclo RAG, rode antes e depois — é o que protege a compatibilidade do índice existente.

Os dublês ficam em `tests/apoio.py`: `EmbutidorFalso`, `RepositorioFalso`, `GeradorFalso`,
`GeradorRoteirizado` (respostas em sequência, guarda os prompts — é o que testa triagem,
reformulação e problematização), `RecuperadorFalso`, `MarcoFalso`, `ColetorFalso`.

Formatação e lint: `ruff format src/ tests/ main.py` e `ruff check src/ tests/ main.py`.

## Arquivos que você NÃO deve ler ou varrer em massa

São artefatos gerados, não fonte. Consulte-os por amostragem (`head`, `ls | wc -l`), nunca
inteiros nem com grep recursivo:

- `data/corpus_uesp/` — 8896 arquivos `.txt`
- `data/chunks.jsonl` — ~50 MB
- `data/qdrant_storage/` — dados binários do Qdrant

## Dependências

`pip3 install -r requirements.txt`. Instalação global, sem virtualenv (Python 3.14). O projeto não
é empacotado: `main.py` põe `src/` no `sys.path` e roda direto do clone.
