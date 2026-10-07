# IA Freiriana — protótipo de RAG local (Fase 2)

Pipeline RAG que roda inteiramente na máquina local: download de corpus →
chunking → embedding/indexação → recuperação → geração. Protótipo da **Fase 2**
do projeto IA Freiriana (Instituto Paulo Freire).

**Documentação:** o [índice dos documentos](docs/README.md) diz por onde começar.
Os principais são a [arquitetura](docs/arquitetura.md), o
[estado do desenvolvimento](docs/estado-do-desenvolvimento.md) e o
[plano por fases](docs/00-plano-geral-implementacao.md).

O corpus atual (lore de Elder Scrolls, da UESP) é **descartável** — serve para
exercitar o pipeline com volume real enquanto o acervo do Centro de Referência
Paulo Freire não fica pronto. Trocar de corpus muda a etapa de download e o
nome da coleção, não a arquitetura.

## Começando

```bash
pip3 install -r requirements.txt
podman compose up -d      # Qdrant em localhost:6333 (painel: /dashboard)
ollama pull bge-m3        # embedding, 1024 dimensões
ollama pull qwen2.5:7b    # geração

python3 main.py           # menu interativo — tudo passa por aqui
```

Use **podman**, não docker — em muitas distros `docker` já é o shim dele. O
podman roda rootless, e por isso os volumes usam a flag `:Z` do SELinux.

## Rodando em container

Alternativa à instalação no host: o pipeline inteiro roda em container, e o
Ollama continua no host, onde a GPU dele já está configurada.

```bash
podman compose --profile execucao build rag     # imagem leve, ~250 MB
podman compose run --rm rag                     # menu, igual ao host
podman compose run --rm rag buscar "..."        # ou um subcomando
```

### Com reordenação por cross-encoder

A reordenação melhora bastante a recuperação (95% de recall contra 88%), mas
precisa de `torch`, que é pesado e **específico do seu acelerador**. Descubra
qual a sua máquina precisa e construa:

```bash
python3 main.py acelerador                      # o que esta máquina tem

TORCH_INDEX="$(python3 main.py acelerador --indice)" \
GPU_ARCH="$(python3 main.py acelerador --arquitetura)" \
  podman compose --profile gpu build rag-gpu

podman compose --profile gpu run --rm rag-gpu   # menu, com reordenação
```

O `GPU_ARCH` é opcional e vale a pena: o `torch` embute kernels de **todas** as
GPUs suportadas, e descartar as que você não tem economiza vários gigabytes.
Sem os dois argumentos, a imagem sai com `torch` de CPU — funciona em qualquer
hardware, mas a reordenação custa segundos em vez de décimos.

Confira que deu certo com `podman compose --profile gpu run --rm rag-gpu ambiente`:
a linha **`PyTorch e a GPU`** diz se o acelerador foi mesmo encontrado. Ela
importa porque o wheel errado instala sem reclamar e cai para CPU em silêncio.

### O que roda onde

| | Onde | Por quê |
|---|---|---|
| Qdrant | container | serviço, sobe com `compose up -d` |
| Ollama | **host** | a GPU dele já está configurada; containerizar custaria a imagem ROCm e o re-download dos modelos |
| Pipeline | container | isola as dependências |
| Código | **host**, montado no container | editar e testar sem reconstruir |

Os serviços `rag` usam rede do host, então alcançam Ollama e Qdrant por
`localhost` sem configuração extra. Os dados (`data/`) e o conteúdo editável
(`marcos/`, `avaliacao/`) entram por montagem e sobrevivem à troca de imagem.

## Como usar

Há uma porta de entrada só, `main.py`, com duas formas de uso — o menu, para
uso normal, e os subcomandos, para automação. As duas chamam exatamente o mesmo
código.

### Menu interativo

```
python3 main.py
```

```
corpus: 8896 arquivos · chunks: sim · coleção 'uesp_lore_agrupado_2000': 26808 pontos
marco: generico

  1  Verificar ambiente   diagnóstico de serviços e artefatos
  2  Baixar corpus        etapa 1 — rede, demorado
  3  Gerar chunks         etapa 2 — rápido
  4  Indexar              etapa 3 — embedding, muito demorado
  5  Buscar               etapa 4 — só recuperação
  6  Perguntar            etapa 5 — resposta direta
  7  Dialogar             problematiza antes de responder
  8  Avaliar              mede a recuperação contra o gabarito
  9  Marco pedagógico     ver e trocar o marco ativo
  c  Configuração         ver, ajustar e salvar parâmetros
  0  Sair
```

As opções **5**, **6** e **7** abrem um laço de conversa: você digita quantas
perguntas quiser, uma por linha, e volta ao menu com uma linha vazia. As etapas
caras (1 e 4) confirmam antes de começar e mostram progresso.

### Linha de comando

```bash
python3 main.py ambiente                      # diagnóstico
python3 main.py baixar                        # etapa 1 — demorado
python3 main.py chunking                      # etapa 2
python3 main.py chunking --estrategia paragrafo --saida data/x.jsonl   # corte antigo, um chunk por parágrafo
python3 main.py indexar                       # etapa 3 — retoma de onde parou
python3 main.py indexar --recriar             # apaga a coleção e refaz
python3 main.py chunking --saida data/experimento.jsonl   # preserva o chunks.jsonl indexado
python3 main.py buscar "quem são os argonianos?"
python3 main.py buscar "..." --sem-intermediar # sem reformular a pergunta
python3 main.py buscar "..." --k-dinamico 0.9 # ajusta o nº de trechos (padrão: 0.9)
python3 main.py perguntar "o que foi a crise de oblivion?" --k 8
python3 main.py perguntar "..." --direto      # sem problematizar
python3 main.py perguntar                     # modo conversa, com memória ('/nova' esquece)
python3 main.py perguntar --sem-memoria       # modo conversa, cada pergunta sozinha
python3 main.py avaliar --comparar            # recall@k com e sem mediação
python3 main.py avaliar --conversa            # recall dos seguimentos, crus contra reescritos
python3 main.py marcos                        # marcos pedagógicos disponíveis
python3 main.py config                        # configuração e origem de cada valor
python3 main.py config --salvar               # grava em config.toml
python3 main.py --help                        # todos os subcomandos
```

Opções globais: `--colecao NOME`, `--marco NOME`, `--config ARQUIVO`,
`--sem-config` e `--sem-cor`. O código de saída é 0 em sucesso e 1 em falha,
para uso em script.

Sem terminal interativo — pipe, cron, script — `perguntar` responde direto, sem
problematizar: as perguntas devolvidas não teriam para quem ir.

## A ordem das etapas importa

Cada etapa consome o artefato da anterior:

| # | Etapa | Consome | Produz | Custo |
|---|-------|---------|--------|-------|
| 1 | download | API da UESP | `data/corpus_uesp/*.txt` | rede, ~9k páginas |
| 2 | chunking | `data/corpus_uesp/` | `data/chunks.jsonl` | segundos |
| 3 | indexação | `data/chunks.jsonl` | coleção no Qdrant | **horas** |
| 4 | recuperação | coleção | trechos | instantâneo |
| 5 | geração | trechos | resposta | ~segundos a minutos |

A etapa 4 é isolável de propósito: recall@k é avaliável sem gerar uma linha de
texto. **Ao depurar qualidade de resposta, confira a recuperação primeiro** —
se o trecho certo não foi recuperado, nenhum ajuste de prompt conserta a
resposta.

## Estrutura

Visão resumida. A explicação completa, com o fluxo de uma pergunta e os contratos, está em
[docs/arquitetura.md](docs/arquitetura.md).

```
main.py                  ponto de entrada único (menu + CLI)
config.exemplo.toml      modelo do config.toml desta máquina
marcos/                  marcos pedagógicos, em Markdown — ver marcos/LEIA-ME.md
avaliacao/               gabarito da avaliação de recuperação
src/rag/
  config.py              todos os parâmetros, mais leitura e escrita do config.toml
  modelos.py             estruturas do domínio (Chunk, TrechoRecuperado, Sessao...)
  protocolos.py          contratos das peças substituíveis
  erros.py               exceções que a interface sabe explicar
  orquestrador.py        o ciclo RAG: recuperação + geração
  marco.py               carrega e valida os marcos pedagógicos
  mediacao.py            reformula e decompõe a pergunta antes da busca
  sessao.py              a máquina de estados que problematiza antes de responder
  conversa.py            memória entre perguntas do modo conversa
  avaliacao.py           mede recall@k contra o gabarito
  acelerador.py          detecta a GPU e diz qual torch instalar
  lexico.py              busca léxica BM25, opcional
  carga.py               modos de carga: total (padrão) ou reduzida (experimental)
  servico.py             composição das dependências
  ambiente.py            diagnóstico
  clientes/              adaptadores: Ollama, Qdrant, UESP, sessão HTTP
  etapas/                as cinco etapas, uma por módulo
  interface/             console, menu, CLI, ações compartilhadas
tests/                   testes com dublês — rodam sem Qdrant nem Ollama
data/                    artefatos gerados (não versionado)
docs/                    plano por fases e decisões técnicas
```

Duas regras sustentam a modularidade, e valem literalmente:

1. **Nenhum módulo de `etapas/` importa outro módulo de `etapas/`.** Eles se
   comunicam por artefato em disco, então refazer uma etapa não afeta as demais.
2. **As etapas dependem de `protocolos.py`, não de `clientes/`.** Trocar Qdrant
   por outro banco vetorial, ou a UESP pelo acervo do IPF, é escrever uma classe
   com os mesmos métodos e mudar uma linha em `servico.py`.

É por isso que os testes rodam sem serviço nenhum de pé — e as duas regras não
dependem de ninguém lembrar delas: `tests/test_estrutura.py` falha se alguma for
quebrada.

## As três camadas sobre o RAG

```
pergunta → sessão dialógica → mediação de consulta → ciclo RAG + marco → resposta
```

**Marco pedagógico.** O que orienta a resposta não está no código: está em
[marcos/](marcos/), em Markdown, versionado e editável por quem não programa —
veja [marcos/LEIA-ME.md](marcos/LEIA-ME.md). O padrão é `generico`, que só serve
ao corpus descartável. `python3 main.py marcos` lista e valida os disponíveis.

**Mediação de consulta.** Uma pergunta composta vira um vetor só, e esse vetor
fica perto de tudo e específico de nada. Antes de embutir, a pergunta é
reformulada em até três consultas independentes, cada uma é buscada, e os
rankings se fundem por RRF. As sub-consultas aparecem na tela.
`--sem-intermediar` desliga, e é assim que se compara com a busca direta.

**Memória de conversa.** No modo conversa (`perguntar` ou `buscar` sem
pergunta, e o menu), um seguimento como "e os Khajiit?" é reescrito como pergunta
completa antes da busca — a reescrita aparece na tela — e as últimas trocas entram
no prompt da resposta. Pergunta que muda de assunto vai intacta. `/nova` esquece o
que foi dito; `--sem-memoria` desliga. Nada da conversa é gravado em disco.

**Sessão dialógica.** Nem toda demanda deve virar resposta direto. A triagem
classifica: dúvida factual vai à busca; pedido de produto acabado e exploração
recebem perguntas de volta antes. O que você responde entra na consulta que vai
à recuperação — problematizar melhora a busca, não só a forma. Enter em branco
pula, e `--direto` desliga.

## Avaliação

Sem medir, toda mudança no chunking, no `k` ou na mediação é troca no escuro.
`avaliar` roda um gabarito de perguntas com as páginas que deveriam ser
recuperadas e devolve `recall@k`, cobertura e MRR — **sem gerar uma linha de
texto**, porque recuperação e geração têm correções opostas e não devem ser
medidas juntas.

```bash
python3 main.py avaliar --comparar
```

A qualidade da resposta gerada não é medida automaticamente, e isso é
deliberado: o modo de falha que importa — texto bem articulado e vazio — é
invisível para métrica textual, e um modelo julgando tende a premiá-lo. Essa
camada é rubrica humana.

O estado atual das medições está em
[docs/estado-do-desenvolvimento.md](docs/estado-do-desenvolvimento.md).

## Configuração

Os padrões ficam em [src/rag/config.py](src/rag/config.py), agrupados por etapa.
Por cima deles entra um `config.toml` opcional, e por cima dele as flags:

```
padrões do código  →  config.toml  →  flags e menu
```

O arquivo guarda **só o que difere do padrão**, então apagá-lo devolve o
comportamento documentado. Comece copiando
[config.exemplo.toml](config.exemplo.toml), ou ajuste pelo menu e grave com
`python3 main.py config --salvar`. `python3 main.py config` mostra de onde vem
cada valor em vigor.

## Testes

```bash
python3 -m unittest discover -s tests -t tests
```

289 testes, nenhum precisando de Qdrant, Ollama ou rede: as dependências
externas entram como dublês (`tests/apoio.py`), o que só é possível porque as
etapas dependem dos protocolos.
