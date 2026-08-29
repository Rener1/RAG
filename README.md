# IA Freiriana — protótipo de RAG local (Fase 2)

Pipeline RAG que roda inteiramente na máquina local: download de corpus →
chunking → embedding/indexação → recuperação → geração. Protótipo da **Fase 2**
do projeto IA Freiriana (Instituto Paulo Freire). O plano completo por fases
está em [docs/](docs/).

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

Use **podman**, não docker: o arquivo se chama `docker-compose.yml` por
convenção de nome apenas, e o volume usa a flag `:Z` do SELinux.

## Como usar

Há uma porta de entrada só, `main.py`, com duas formas de uso — o menu, para
uso normal, e os subcomandos, para automação. As duas chamam exatamente o mesmo
código.

### Menu interativo

```
python3 main.py
```

```
corpus: 8896 arquivos · chunks: sim · coleção 'uesp_lore': 69285 pontos
marco: generico

  1  Verificar ambiente   diagnóstico de serviços e artefatos
  2  Baixar corpus        etapa 1 — rede, demorado
  3  Gerar chunks         etapa 2 — rápido
  4  Indexar              etapa 3 — embedding, muito demorado
  5  Buscar               etapa 4 — só recuperação
  6  Perguntar            etapa 5 — resposta direta
  7  Dialogar             problematiza antes de responder
  8  Marco pedagógico     ver e trocar o marco ativo
  9  Configuração         ver, ajustar e salvar parâmetros
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
python3 main.py chunking --estrategia paragrafo_agrupado
python3 main.py indexar                       # etapa 3 — retoma de onde parou
python3 main.py indexar --recriar             # apaga a coleção e refaz
python3 main.py chunking --saida data/experimento.jsonl   # preserva o chunks.jsonl indexado
python3 main.py buscar "quem são os argonianos?"
python3 main.py buscar "..." --sem-intermediar # sem reformular a pergunta
python3 main.py perguntar "o que foi a crise de oblivion?" --k 8
python3 main.py perguntar "..." --direto      # sem problematizar
python3 main.py perguntar                     # modo conversa
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

```
main.py                  ponto de entrada único (menu + CLI)
config.exemplo.toml      modelo do config.toml desta máquina
marcos/                  marcos pedagógicos, em Markdown — ver marcos/LEIA-ME.md
src/rag/
  config.py              todos os parâmetros, mais leitura e escrita do config.toml
  modelos.py             estruturas do domínio (Chunk, TrechoRecuperado, Sessao...)
  protocolos.py          contratos das peças substituíveis
  erros.py               exceções que a interface sabe explicar
  orquestrador.py        o ciclo RAG: recuperação + geração
  marco.py               carrega e valida os marcos pedagógicos
  mediacao.py            reformula e decompõe a pergunta antes da busca
  sessao.py              a máquina de estados que problematiza antes de responder
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

**Sessão dialógica.** Nem toda demanda deve virar resposta direto. A triagem
classifica: dúvida factual vai à busca; pedido de produto acabado e exploração
recebem perguntas de volta antes. O que você responde entra na consulta que vai
à recuperação — problematizar melhora a busca, não só a forma. Enter em branco
pula, e `--direto` desliga.

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

158 testes, nenhum precisando de Qdrant, Ollama ou rede: as dependências
externas entram como dublês (`tests/apoio.py`), o que só é possível porque as
etapas dependem dos protocolos.
