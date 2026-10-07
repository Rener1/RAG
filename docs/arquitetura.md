# Arquitetura

> [Índice dos documentos](README.md) · [Estado do desenvolvimento](estado-do-desenvolvimento.md) ·
> [README do repositório](../README.md)

Este documento descreve como o código deste repositório é organizado e por quê. É para quem vai
mantê-lo ou chega agora no projeto.

Ele **não traz números**: as medições que justificam cada decisão estão no
[estado do desenvolvimento](estado-do-desenvolvimento.md), e aqui aparecem só como link. Assim,
quando uma medição mudar, há um lugar só para atualizar.

---

## 1. O que o sistema faz

Um pipeline RAG local. Ele baixa um corpus, corta os documentos em trechos, gera um vetor por trecho
e indexa tudo num banco vetorial. Diante de uma pergunta, recupera os trechos mais pertinentes e
pede a um modelo de linguagem que responda **a partir deles**, citando a fonte.

Sobre esse ciclo, três camadas próprias do projeto:

- a **sessão dialógica**, que problematiza antes de responder;
- a **mediação de consulta**, que decompõe a pergunta;
- o **marco pedagógico**, que orienta a resposta e fica fora do código.

```
                 ┌────────────── interface: menu · CLI ───────────────┐
                 │            (as duas chamam interface/acoes.py)      │
                 └──────────────────────────┬─────────────────────────┘
                                            │
                         servico.py — monta as peças e as entrega prontas
                                            │
   ┌────────────────────────────────────────┼────────────────────────────────────┐
   │ PIPELINE DE DADOS (offline)            │  CICLO DE PERGUNTA (online)         │
   │                                        │                                     │
   │ download → chunking → indexação        │  Dialogo (sessao.py)                │
   │    │          │           │            │     ↓ consulta consolidada          │
   │  .txt    chunks.jsonl   Qdrant ────────┼─→ IntermediadorDeConsulta           │
   │                                        │     ↓ N sub-consultas, fusão RRF    │
   │                                        │  Recuperador (+ BM25, reordenador)  │
   │                                        │     ↓ trechos                       │
   │                                        │  MotorRag + marco → Gerador         │
   └────────────────────────────────────────┴─────────────────────────────────────┘
        clientes/: Ollama (embedding e geração) · Qdrant · UESP · reordenador (torch)
```

O corpus atual, a lore de Elder Scrolls, é **descartável**. Ele existe para exercitar o pipeline
com volume real enquanto o acervo do Instituto não chega. A arquitetura foi desenhada para que a
troca de corpus mude o download e a coleção, não a estrutura (ver §8).

---

## 2. Duas regras que sustentam tudo

1. **Nenhum módulo de `etapas/` importa outro módulo de `etapas/`.** As etapas se comunicam por
   arquivo em disco. É isso que permite refazer uma etapa (recortar de outro jeito, por exemplo)
   sem tocar nas outras.
2. **As etapas dependem de [`protocolos.py`](../src/rag/protocolos.py), nunca de `clientes/`.**
   Uma etapa recebe "algo que embute texto", não "o cliente do Ollama". Trocar o banco vetorial é
   escrever outra classe com os mesmos métodos e mudar uma linha em
   [`servico.py`](../src/rag/servico.py).

As duas são verificadas pela suíte: [`tests/test_estrutura.py`](../tests/test_estrutura.py)
percorre os imports com `ast` e falha se uma delas quebrar. A segunda regra é também o que deixa os
testes rodarem sem Qdrant nem Ollama: eles usam dublês (`tests/apoio.py`) no lugar dos clientes.

**Consequência prática:** código que compõe recuperação com geração não pode morar em `etapas/`,
porque obrigaria uma etapa a importar outra. Por isso `orquestrador.py`, `mediacao.py`,
`sessao.py`, `marco.py`, `avaliacao.py`, `lexico.py` e `carga.py` ficam na raiz do pacote.

---

## 3. Onde cada coisa mora

```
main.py                 fino: ajusta sys.path e delega à interface
config.toml             sobreposição de configuração desta máquina (não versionado)
marcos/*.md             marcos pedagógicos — dado versionado, editável sem programar
avaliacao/casos.jsonl   gabarito da avaliação de recuperação
src/rag/
  config.py             todos os parâmetros, com padrão e justificativa; lê e grava config.toml
  modelos.py            estruturas do domínio: Chunk, TrechoRecuperado, Resposta, Sessao…
  protocolos.py         os contratos (§5)
  erros.py              exceções que a interface sabe explicar, sempre com sugestão de conserto
  servico.py            composição: o único lugar onde classes concretas encontram protocolos
  orquestrador.py       MotorRag — recuperação + orçamento de contexto + geração
  mediacao.py           IntermediadorDeConsulta — reformula, decompõe, funde por RRF
  sessao.py             Dialogo — triagem e problematização antes de responder
  marco.py              carrega e valida os marcos pedagógicos
  lexico.py             BM25 e a fusão dele com a busca densa (desligado por padrão)
  avaliacao.py          recall@k, cobertura, MRR e cortes contra o gabarito
  carga.py              limitador de carga do hardware
  ambiente.py           diagnóstico de serviços, modelos e artefatos
  acelerador.py         detecta a GPU e diz qual build do torch instalar
  etapas/               download · chunking · indexacao · recuperacao · geracao
  clientes/             Ollama · Qdrant · UESP · reordenador · sessão HTTP com repetição
  interface/            console · menu · cli · acoes
tests/                  suíte com dublês — sem serviço nem rede
data/                   artefatos gerados (não versionados)
```

---

## 4. Os dois fluxos

### 4.1 Pipeline de dados (offline)

Cada etapa lê o artefato da anterior e grava o seu. Pode ser refeita isoladamente.

| Etapa | Lê | Grava | Notas |
|---|---|---|---|
| [`download`](../src/rag/etapas/download.py) | API MediaWiki da UESP | `data/corpus_uesp/*.txt` | Será substituída para o acervo do IPF (§8) |
| [`chunking`](../src/rag/etapas/chunking.py) | os `.txt` | `data/chunks.jsonl` | Estratégia plugável (`ESTRATEGIAS`). Grava em arquivo temporário e troca no fim: uma interrupção não corrompe o anterior |
| [`indexacao`](../src/rag/etapas/indexacao.py) | `chunks.jsonl` | coleção no Qdrant | Retoma de onde parou; confere a dimensão do vetor **antes** de processar; um lote que falha não derruba os outros |

Um chunk carrega a sua proveniência (`chunk_id`, documento, título e os campos reservados para
página, seção, offset e restrição de uso). Esses campos vão para o payload do Qdrant. É de lá que
a citação e, futuramente, o filtro de restrição leem, porque o banco vetorial não faz junção com
outra tabela.

### 4.2 Ciclo de uma pergunta (online)

```
pergunta
  │
  ├─ Dialogo.classificar ────── triagem: dúvida factual, exploração ou produto acabado
  │     dúvida factual → segue direto
  │     as outras → Dialogo.problematizar: perguntas de volta, ancoradas numa busca prévia;
  │                 as respostas da pessoa entram na consulta
  │
  ├─ IntermediadorDeConsulta.buscar
  │     decompõe em até N sub-consultas (uma só, se a pergunta trata de um assunto só)
  │     busca cada uma → funde os rankings por RRF → reordena UMA vez, contra a pergunta original
  │
  ├─ Recuperador.buscar (para cada sub-consulta)
  │     embute → busca no Qdrant → [funde com BM25] → [reordena] → decidir_quantidade
  │
  ├─ MotorRag
  │     descarta o que não cabe na janela do modelo (orçamento de contexto)
  │     monta o prompt com o marco → Gerador.gerar (streaming)
  │
  └─ interface: mostra as fontes antes da resposta; validar_citacoes confere cada [Fonte N]
```

Quatro decisões de desenho nesse caminho:

- **As camadas se empilham sem se conhecer.** O `IntermediadorDeConsulta` cumpre o mesmo
  protocolo do `Recuperador` (`RecuperadorDeTrechos`) e o envolve por injeção. O `MotorRag` não
  sabe se há mediação, e o `Dialogo` não sabe como a busca funciona. Por isso cada camada pode ser
  desligada (`--sem-intermediar`, `--direto`), e é assim que se mede o efeito de cada uma.
- **Tropeço em camada opcional vira caminho mais simples, nunca exceção.** Se a mediação não
  consegue decompor, vira busca direta. Se o reordenador falha, fica a ordem vetorial. A
  recuperação tem de continuar avaliável sozinha.
- **O orçamento de contexto mora no `MotorRag`, não no montador do prompt.** A lista de trechos
  mostrada na tela tem de ser a mesma que foi ao modelo; senão a validação de citações aprovaria
  uma fonte que o modelo nunca viu.
- **A quantidade de trechos é decidida numa função só,** `decidir_quantidade`, usada pela busca
  direta e pela mediação. Já esteve duplicada, e um conserto valeu só num dos lados.

---

## 5. Contratos — `protocolos.py`

São `Protocol` (tipagem estrutural): uma implementação nova não herda de nada, só precisa ter os
métodos com a mesma forma.

| Protocolo | Promete | Implementação hoje | Dublê nos testes |
|---|---|---|---|
| `Embutidor` | `embutir(textos) → vetores`, `dimensao` | `ClienteOllama` (bge-m3) | `EmbutidorFalso` |
| `Gerador` | `gerar(prompt) → pedaços de texto` | `GeradorOllama` (qwen2.5:7b) | `GeradorFalso`, `GeradorRoteirizado` |
| `RepositorioVetorial` | criar coleção, inserir, buscar, contar | `RepositorioQdrant` | `RepositorioFalso` |
| `Reordenador` | `reordenar(pergunta, trechos)` | `ReordenadorLocal` (cross-encoder via torch) | `ReordenadorFalso` |
| `RecuperadorDeTrechos` | `buscar(pergunta, k)` | `Recuperador`, `RecuperadorHibrido`, `IntermediadorDeConsulta` | `RecuperadorFalso` |
| `ColetorDeCorpus` | listar e baixar documentos | `ColetorUESP` | `ColetorFalso` |
| `MarcoPedagogico` | seções e metadados do marco | `Marco` | `MarcoFalso` |

**Divergência registrada com o plano.** O contrato da
[Fase 0 §3.5](fase-0-desenho-e-contratos.md) pede um runtime de inferência "compatível com a API
da OpenAI". O código fala a API **nativa** do Ollama (`/api/embed`, `/api/generate`). Isso é
contornável, porque trocar de runtime é escrever outro cliente para os mesmos dois protocolos, mas
é uma diferença real e está registrada aqui para não se perder.

---

## 6. Composição e configuração

### 6.1 `servico.py` — onde as peças se encontram

`Servico` é a raiz de composição. Ele constrói cada cliente sob demanda (`cached_property`), de
modo que rodar só o chunking não exige Qdrant nem Ollama de pé. Também decide as combinações:

- com a mediação ligada, quem reordena é ela, sobre a lista fundida; com ela desligada, é o
  `Recuperador`, e nunca os dois;
- com o BM25 ligado, o `RecuperadorHibrido` envolve a busca densa;
- com a carga limitada (`carga.fracao < 1`), embutidor, reordenador e gerador de apoio são
  embrulhados pelo limitador de [`carga.py`](../src/rag/carga.py), um só para o processo inteiro.
  As etapas recebem a peça embrulhada sem saber disso.

### 6.2 Configuração em camadas

```
padrões em config.py  →  config.toml (opcional)  →  flags da CLI / menu
```

- **Os padrões estão no código**, nas dataclasses de [`config.py`](../src/rag/config.py), cada um
  com o comentário que diz por que vale aquilo.
- **O `config.toml` guarda só o que difere do padrão.** Apagá-lo devolve o comportamento
  documentado.
- `python3 main.py config` mostra cada valor e **de onde ele veio** (padrão, arquivo ou flag).
- O menu edita os campos por introspecção, então um campo novo numa dataclass já nasce editável e
  persistível.
- `config.exemplo.toml` é **gerado** das dataclasses, e um teste falha se ele ficar defasado.

### 6.3 Interface

Menu e CLI são duas portas para as mesmas funções de
[`interface/acoes.py`](../src/rag/interface/acoes.py). **Não existe capacidade que só uma das
duas alcance**: ao acrescentar uma, a ação entra em `acoes.py` e é ligada nas duas.

---

## 7. O marco pedagógico

O marco é **dado, não código**: um Markdown com frontmatter em [`marcos/`](../marcos/), carregado
em tempo de execução e editável pelo comitê sem programar ([instruções](../marcos/LEIA-ME.md)).

- Três seções alimentam camadas diferentes: `Decomposição` orienta a mediação; `Triagem` e
  `Problematização` orientam a sessão. As demais entram no prompt da resposta, e uma seção nova
  entra sozinha, sem mudar código.
- Marco quebrado **levanta erro**, em vez de cair num prompt genérico em silêncio.
- `generico` é o marco ativo por padrão e não tem valor pedagógico. `freiriano` é um esqueleto à
  espera do comitê.

---

## 8. Avaliação e operação

- **A avaliação mede só a recuperação** (recall@k, cobertura, MRR e quantos casos o orçamento de
  contexto cortaria), sem gerar uma linha de texto. A qualidade da resposta é rubrica humana, por
  decisão do plano ([Fase 3](fase-3-avaliacao-e-servidor.md) §5 e §8).
- **Implantação:** o Qdrant roda em container; o Ollama roda no host, onde a GPU já está
  configurada. A aplicação roda no host ou em container com rede do host. A variante `rag-gpu`
  traz o torch para o reordenador. Os detalhes estão no [README](../README.md#rodando-em-container).
- **Carga no hardware:** `--carga F` descansa uma fração do tempo depois de cada lote, e
  `carga.threads_de_cpu` limita as threads do Ollama. As medições e um efeito ainda não explicado
  estão no [estado](estado-do-desenvolvimento.md).

---

## 9. Onde o acervo do Instituto vai entrar

O desenho está em [esquema de metadados](esquema-de-metadados.md) §8. Em resumo, o que muda:

| O quê | Como |
|---|---|
| Fonte do corpus | Etapa nova `etapas/catalogo.py`: lê a exportação do DSpace e as tabelas de política e grava `data/catalogo.jsonl`. O chunking passa a ler esse arquivo. Continua sendo comunicação por disco |
| Coleção | `uesp_lore_*` → `corpus_ipf`, por configuração |
| Filtro de restrição de uso | `RepositorioVetorial.buscar` passa a receber filtro, aplicado **dentro** da query e por lista de permitidos. Vazio passa a significar "não classificado", e não classificado não é recuperado |
| Citação | `pagina` e `uri` no `TrechoRecuperado`; a citação vira link verificável |
| Recorte | Corte sensível à estrutura, por seção ([caminhos de recorte](recorte-de-conteudo-caminhos.md), A1) |

O que **não** muda: as duas regras do §2, os protocolos, a composição e as camadas de sessão,
mediação e marco.
