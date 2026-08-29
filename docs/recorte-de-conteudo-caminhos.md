# Recorte de conteúdo — caminhos possíveis

**Status:** documento de decisão técnica, não do plano por fases. Complementa
`fase-1-corpus.md` §4.6–4.8 e `fase-2-prototipo.md` §4.5 com o que é
implementável neste repositório, quanto custa cada caminho, e em que ordem.

---

## O problema

O corte hoje é por parágrafo (`ESTRATEGIAS["paragrafo"]` em
`src/rag/etapas/chunking.py`): um chunk por bloco separado por linha em branco,
parágrafo abaixo de 60 caracteres descartado, acima de 2000 subdividido. É
insensível ao contexto em três sentidos:

1. **Não sabe onde está.** Um parágrafo do meio de "Mythology › Altmer" chega ao
   índice sem nenhuma marca de que pertence àquela seção. O embedding vê só o
   parágrafo, e um trecho que diz "eles chegaram depois" não diz quem chegou.
2. **Corta no meio do argumento.** O limite é a linha em branco, não a unidade
   de sentido — e os docs são explícitos: "um trecho cortado no meio de um
   raciocínio de Freire perde o sentido que o torna citável".
3. **Descarta o curto.** Parágrafo com menos de 60 caracteres some. Em artigo de
   diálogo ou lista de citações, isso descarta conteúdo real.

E falta a proveniência que a citação verificável exige: página e offset.

## A restrição que organiza tudo

Mudar o texto dos chunks muda os vetores, e trocar os vetores é reindexar. Hoje
são 69285 chunks e horas de processamento. **Daí a regra: toda mudança que
invalida o índice espera pela próxima reindexação obrigatória, e todas entram
juntas.** A troca para o acervo do IPF é essa janela — ela obriga a reindexar de
qualquer jeito, e é quando as mudanças estruturais saem de graça.

Enquanto isso, experimento nenhum toca em `data/chunks.jsonl` nem na coleção
`uesp_lore`:

```bash
python3 main.py chunking --estrategia secao --saida data/chunks_secao.jsonl
python3 main.py indexar --colecao uesp_lore_secao
python3 main.py buscar "..." --colecao uesp_lore_secao
```

## A mudança habilitadora

Três dos caminhos abaixo precisam que o corte saiba onde cada trecho estava.
Isso é interno à etapa e não vai para `modelos.py`:

```python
# src/rag/etapas/chunking.py
@dataclass(frozen=True, slots=True)
class TrechoCortado:
    texto: str
    caminho_secao: tuple[str, ...] = ()   # ("Mythology", "Altmer")
    inicio: int = 0                        # offset no corpo do documento
    fim: int = 0

@dataclass
class ResultadoCorte:
    trechos: list[TrechoCortado]
    teve_paragrafo_gigante: bool = False

    @property
    def textos(self) -> list[str]:         # mantém os testes atuais de pé
        return [t.texto for t in self.trechos]
```

Os campos de destino já existem em `Chunk` (`pagina`, `secao`, `inicio`, `fim`,
`versao_embedding`, `restricao_uso`) — foram acrescentados de forma aditiva, e
campo em branco não é gravado, então o `chunks.jsonl` atual continua byte a byte
idêntico e o índice continua válido.

---

## Os caminhos

| # | Caminho | O que muda | Invalida o índice? | Custo |
|---|---|---|---|---|
| **A5** | **Proveniência por chunk** — `pagina`, `secao`, `inicio`, `fim`, `versao_embedding`, `restricao_uso` | `Chunk`, `como_dicionario`, `de_dicionario` | **não** | ✅ feito |
| **A1** | **Corte por seção/cabeçalho** | `ESTRATEGIAS["secao"]` + `TrechoCortado` | sim | 1 função + 1 regex + ~6 testes |
| **A4** | **Enriquecimento de contexto** no texto embutido | `Chunk.texto_para_embutir()`, usado só na indexação | sim (vetores) | ~10 linhas |
| **A2** | **Janela deslizante com sobreposição** | `ESTRATEGIAS` + `sobreposicao` em `ConfigChunking` | sim | baixo, mas +25–40% de chunks |
| **A3** | **Pai/filho (small-to-big)** | `chunk_pai_id` + protocolo, ou `texto_pai` no payload | sim | alto |
| **A6** | **Reordenação pós-busca** por cross-encoder | só a camada de recuperação | **não** | modelo e dependência novos |

### A5 — proveniência por chunk *(implementado)*

Os campos existem, com valor neutro, e só são gravados quando preenchidos. É o
pré-requisito de `fase-1-corpus.md` §4.7 — "a decisão de ingestão que mais dói se
for esquecida, porque exige reprocessar tudo" — e do filtro de restrição de uso
aplicado dentro da query (`fase-2-prototipo.md` §4.4). Quem os preenche é a
estratégia de corte sensível à estrutura, quando ela entrar.

### A1 — corte por seção *(recomendado como próximo)*

Reconhece `^(={2,6})\s*(.+?)\s*=*$` (wikitexto) e `^(#{2,6})\s+(.+)$`
(markdown, que é o formato de saída provável da extração de PDF do acervo real).
Seção acima do teto cai no `dividir_paragrafo_gigante` que já existe; o texto
antes do primeiro cabeçalho vira uma seção sem nome.

**É implementável e testável hoje**: `mwparserfromhell.strip_code()` preserva os
cabeçalhos `== Seção ==` nos `.txt` do corpus da UESP — conferido em
`data/corpus_uesp/Lore_Aedra.txt`.

Por que é o próximo, e não os outros: é a que os docs pedem nominalmente
("quebrar por seção/argumento, não por contagem cega"), e é a única que serve aos
dois corpora com o mesmo código. A2 e A3 sobre texto cru se comportam igual em
qualquer corpus, e por isso não ensinam nada sobre o acervo real antes dele
chegar.

### A4 — enriquecimento de contexto

Embutir `"{titulo_pagina} › {caminho_secao}\n{texto}"` e exibir só o texto. Duas
variantes: prefixar dentro de `Chunk.texto` suja a citação mostrada ao usuário;
um `Chunk.texto_para_embutir()` derivado, usado apenas em `indexacao.executar`,
mantém o payload limpo. Só rende se A1 existir — sem seção não há o que
prefixar — e é onde está a maior parte do ganho de recall.

### A2 — janela deslizante

O mais simples de escrever e o pior negócio agora: aumenta a contagem de chunks
em 25–40%, o que multiplica pelo mesmo fator as horas de indexação, e agrava a
redundância no top-k — exatamente o que a diretriz de mostrar posições
divergentes quer combater. Faz sentido *dentro* de uma seção, depois de A1; sobre
o fluxo bruto de bytes, não.

### A3 — pai/filho

Indexa o filho pequeno (bom para a similaridade) e entrega o pai grande ao prompt
(bom para o contexto). Maior retorno esperado no acervo real, onde a unidade é a
obra teórica com argumento longo. Duas implementações: `RepositorioVetorial.obter_por_ids`
(mudança de protocolo — exige atualizar `tests/apoio.RepositorioFalso` no mesmo
commit) ou `texto_pai` no payload (sem mudar protocolo, 2–3× o armazenamento).
Depende de A1: sem seção, "pai" é um recorte arbitrário.

### A6 — reordenação pós-busca

Buscar 3k, reordenar com um cross-encoder, entregar k. É o único da lista que
melhora o recorte efetivo **sem reindexar**, porque age depois da busca. O preço
é um modelo novo (`bge-reranker` ou equivalente) e mais uma dependência de
runtime — por isso não é o primeiro passo, apesar de não tocar no índice.

---

## Ordem recomendada

1. **Feito:** A5. Aditivo, sem reindexação.
2. **Próximo:** A1 com A4 acoplado, em coleção separada, comparado com a atual.
3. **Na troca para o acervo do IPF:** preencher página e offset na mesma
   reindexação que a troca de corpus já obriga.
4. **Depois, com medição:** A2, A3 e A6, avaliados pelo harness da Fase 3. Sem
   `recall@k` medido, trocar chunking é trocar no escuro.

## Um item fora da lista

`ConfigChunking.tamanho_maximo` é 2000 caracteres e precisa ser conferido contra
a janela de entrada do bge-m3. `fase-2-prototipo.md` §7 marca o truncamento
silencioso como risco da fase: pedaço maior que a janela é cortado sem erro
nenhum, e a cauda desaparece da busca. A verificação é barata — embutir um chunk
longo, embutir só a cauda dele, e comparar.
