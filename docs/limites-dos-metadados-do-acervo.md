# Limites dos metadados do acervo

> [Índice dos documentos](README.md) · [Esquema de metadados](esquema-de-metadados.md) · [Fase 1 — Corpus](fase-1-corpus.md)

**Data:** 2026-09-21
**Status:** análise técnica. Fundamenta a versão 0.2 de
[esquema-de-metadados.md](esquema-de-metadados.md).
**A quem se dirige:** equipe técnica (tudo), comitê pedagógico (§2.2, §2.4, §3) e direção
(§2.5, §2.6 e §6 — são decisões institucionais, não técnicas).

---

## 1. O ponto de partida

Fomos informados de que o acervo tem os metadados abaixo e de que eles **não serão modificados
nem preenchidos manualmente**:

```
id, collection,
dc.contributor.author (+ [], [en], [es], [pt], [pt_BR]), dc.contributor.other[],
dc.coverage.spatial (+ [], [es], [pt_BR]),
dc.date.accessioned, dc.date.available, dc.date.issued (+ variantes),
dc.description, dc.description.abstract, dc.description.provenance, (+ variantes)
dc.format.medium[pt_BR], dc.format.mimetype[pt_BR],
dc.identifier.citation, .isbn[], .issn, .level[], .other, .uri (+ variantes),
dc.language.iso, dc.publisher, dc.relation.ispartofseries, dc.rights[],
dc.subject (+ .other, [en], [es], [fr], [pt_BR]),
dc.title, dc.title.alternative (+ [en], [es], [pt_BR]),
dc.type (+ [pt_BR])
```

É uma **exportação CSV de DSpace** — reconhecível por `id`, `collection`,
`dc.description.provenance` e pelos qualificadores de idioma. Isso muda a natureza do problema
que o esquema v0 resolvia: o acervo não é uma caixa de documentos a catalogar, é um
**repositório institucional já catalogado, com outro esquema, que não vamos alterar**.

Este documento compara esses metadados com o que está planejado — o PDF oficial
(`IPF - Projeto desenvolvimento IA Freiriana.pdf`) como referência, e os documentos de fase e o
esquema v0 como derivados dele — e diz o que pode e o que não pode ser implementado, e por quê.

### 1.1 O que ainda não sabemos

Esta análise viu **os nomes das colunas, não os valores**. Três conclusões dependem de valores e
estão marcadas no texto. A verificação é barata e deve vir antes de qualquer decisão:

```bash
# frequência dos valores de uma coluna — repetir para cada coluna da lista abaixo
python3 -c "
import csv, collections, sys
coluna = sys.argv[2]
with open(sys.argv[1], newline='', encoding='utf-8') as f:
    contagem = collections.Counter(linha.get(coluna, '') for linha in csv.DictReader(f))
for valor, n in contagem.most_common(40):
    print(f'{n:6}  {valor[:100]!r}')
" acervo.csv 'dc.rights[pt_BR]'
```

| Coluna | O que decide |
|---|---|
| `dc.rights[]`, `dc.rights[pt_BR]` | Se `restricao_uso` é derivável por documento (§2.1) |
| `dc.type`, `dc.type[pt_BR]` | Como o vocabulário mapeia nos cinco tipos (§2.3) |
| `collection` | Quantas coleções há — o tamanho da tabela de política (§4) |
| `dc.identifier.level[]` | Se é nível acadêmico (proxy de confiabilidade) ou outra coisa |
| `dc.language.iso` | Se o código é `pt`, `por` ou `pt_BR`, e quanto do acervo não é português |
| `dc.identifier.uri` | Se todo item tem handle |

E um pressuposto: **os arquivos (bitstreams) vêm junto do CSV**. Sem os PDFs não há corpus — o
CSV é catálogo, não conteúdo. Tudo abaixo assume que vêm.

---

## 2. As limitações, em ordem de gravidade

### 2.1 `restricao_uso` — a única com consequência de segurança

É a única limitação com risco de vazamento, e a única cuja gravidade depende de valores que ainda
não vimos.

- **Se `dc.rights` for vocabulário** (`Acesso Aberto` / `Acesso Restrito` / `Acesso
  Embargado`, comum em repositórios brasileiros): `restricao_uso` é derivável por tabela de
  mapeamento, com uma decisão por *valor distinto*, não por documento. A limitação desaparece.
- **Se for texto livre de licença** ("Creative Commons Atribuição 4.0…", "© Instituto Paulo
  Freire", vazio): não há derivação segura, e casar string é o "meio-termo" que o princípio 5 do
  esquema proíbe. A saída é declarar a restrição **por coleção** (§4).

Em qualquer dos dois casos, duas coisas continuam valendo e não dependem do acervo:

- o filtro é por **lista de permitidos**, dentro da query (esquema §7.3);
- `src/rag/modelos.py` documenta `restricao_uso: str = ""  # vazio = público`. Essa semântica
  tem de inverter antes de o primeiro documento do IPF entrar no índice: vazio passa a ser *não
  classificado*, e não classificado não é recuperado.

### 2.2 `contexto` — a perda mais séria para o pedagógico, e sem substituto

`dc.description.abstract` é **resumo do conteúdo**. `contexto` é **situação de produção**: quem
produziu, para quem, a serviço de quê. O esquema v0 já antecipava a confusão (§8: "não é resumo
do conteúdo, é a situação de produção").

O que isso quebra, nas palavras do PDF oficial (p. 5):

> Assumir posição e mostrar a disputa. Uma perspectiva freiriana é assumidamente política. O
> sistema deve dizer de onde fala e apresentar as posições em disputa, em vez de simular
> neutralidade técnica.

Sem `contexto`, o sistema não sabe de onde cada documento fala. O caso que o esquema v0 dá como
exemplo é exatamente o que se perde: um relatório encomendado por uma secretaria e uma crítica
publicada sobre a mesma política não são a mesma coisa, e nada no texto extraído diz qual é qual.

**Mitigação parcial:** `collection`, `dc.publisher` e `dc.relation.ispartofseries` dão a
procedência institucional, e um texto de contexto **por coleção** cobre o gênero do material. O
que não se recupera é a distinção entre documentos da mesma coleção.

### 2.3 `tipo` — o vocabulário do acervo provavelmente não é o nosso

A tipologia `obra / relatorio / normativo / academico / memoria` foi desenhada para o acervo
físico do Centro de Referência — caixas, atas, relatórios de assessoria. Um repositório DSpace
guarda **produção publicada**.

Consequência provável (a confirmar com a contagem de `dc.type[pt_BR]`): `academico` e `obra`
dominam; `memoria` e `normativo` quase não aparecem.

- **Efeito positivo:** se só dois ou três tipos aparecem, só duas ou três estratégias de chunking
  (`fase-1` §4.6) precisam existir.
- **Efeito negativo:** `tipo` é o único campo além do identificador cujo erro custa reindexação
  (esquema §3, nível 2). Um mapeamento automático errado é caro de descobrir. O mapeamento
  `dc.type → tipo` tem de ser **congelado e versionado antes da indexação**.

A pendência §10.2 do esquema muda de natureza: deixa de ser "os cinco valores cobrem o acervo?"
(curadoria, amostra de trinta documentos) e vira "como o vocabulário existente mapeia nos cinco?"
(técnica, contagem de valores, confirmada pela curadoria).

### 2.4 `confiabilidade` — sem base por documento

Não existe coluna, e não é derivável do conteúdo. O que resta é o estrato: `dc.type`,
`collection` e, se for nível acadêmico, `dc.identifier.level`.

A pergunta ao comitê (esquema §10.1) muda de

> *Quantos níveis, com que critério observável, aplicável por dois catalogadores ao mesmo
> documento?*

para

> *Que peso relativo têm os estratos que o acervo já distingue — tese, dissertação, artigo,
> livro, produção institucional?*

A segunda é mais fácil de responder e mais defensável, porque o critério é observável por
construção. O que se perde: um documento excepcional num estrato fraco não tem como ser
promovido.

### 2.5 Registro de verificação de direitos — não existe

O PDF (p. 8) pede: "Verificação de direitos autorais e de uso, documento a documento. Registrar o
que pode ser usado internamente, o que pode ser publicado e o que não pode ser usado."
`fase-1` §6 e §7 transformam isso em entregável e em critério de aceite do portão G1 → 3.

Não há titular, evidência, nem quem verificou e quando. A saída **não é técnica**: é declarar
que *o depósito autorizado no repositório institucional é a evidência de direitos*, registrado
uma vez por coleção, com assinatura e data. Isso é defensável para produção própria de acesso
aberto, e indefensável para material de terceiros depositado sem licença explícita — por isso a
declaração é por coleção, e coleção sem declaração não entra.

### 2.6 Dados pessoais — o requisito não é implementável como está documentado

É o único ponto em que uma funcionalidade documentada **não pode ser entregue**, nem em versão
degradada.

O PDF (p. 8) e `fase-1` §4.5 pedem triagem por documento, **anonimização antes de indexar**,
registro do que foi anonimizado e `vedado` para o que não puder ser anonimizado. Nenhum campo
existe, e nenhum é derivável do catálogo: dado pessoal está **no corpo do texto**.

O que resta:

| Substituto | O que entrega | O que não entrega |
|---|---|---|
| Restringir o escopo a coleções de material já publicado | O material foi tornado público pela própria instituição | Recuperação por IA é tratamento novo; publicação prévia não é consentimento para agregação |
| Triagem automática no texto (CPF, e-mail, telefone, endereço) que **bloqueia** o documento | Pega o dado estruturado | Não anonimiza; não pega o que mais importa — relatos, deliberações, saúde |
| Aceitar o risco, registrado | Honestidade | Nada |

A decisão 3 do PDF (p. 10, "que dados jamais entram no sistema") continua sendo pré-requisito,
mas muda de função: deixa de ser a lista que o curador aplica documento a documento e passa a
definir **quais coleções inteiras entram**.

Um cuidado a mais: `dc.description.provenance`, gerado pelo DSpace, contém o **e-mail de quem
depositou**. É dado pessoal no próprio catálogo, e essa coluna não deve ser lida pelo pipeline.

### 2.7 Fragmentação por idioma — custo de código, não perda

O mesmo campo aparece em até seis colunas (`dc.contributor.author`, `[]`, `[en]`, `[es]`,
`[pt]`, `[pt_BR]`). Não há perda de informação, mas há uma camada de normalização que o esquema
v0 não previa:

- **coalescência com prioridade declarada** — `[pt_BR]` → `[pt]` → sem qualificador → `[]` →
  `[es]` → `[en]` → `[fr]` — gravando **de que coluna veio** cada valor, senão conflito entre
  colunas fica invisível;
- **o separador multivalorado do DSpace é `||`**, não o `;` do esquema v0 §7.1;
- o mesmo autor pode aparecer grafado diferente em duas colunas do mesmo item.

### 2.8 OCR — registro só do que nós processarmos

`fase-1` §4.2 pede ferramenta e versão de OCR por documento. Para PDF que já chegou com camada de
texto, não sabemos quem o gerou nem com que qualidade. A revisão amostral passa a ser feita **por
coleção**, sobre o texto extraído, e o registro de ferramenta só existe para o que passar pelo
nosso OCR.

### 2.9 O que não é limitação

`pagina`, `secao`, `inicio` e `fim` vêm da **extração do PDF**, não do catálogo. A proveniência
por chunk (`fase-1` §4.7) continua implementável exatamente como
[recorte-de-conteudo-caminhos.md](recorte-de-conteudo-caminhos.md) descreve (caminho A1).

---

## 3. Funcionalidades documentadas: veredito

✅ implementável como documentada · ⚠️ em versão degradada · ❌ não implementável a partir destes
metadados

### 3.1 PDF oficial

| Página | Funcionalidade | | Motivo |
|---|---|---|---|
| 5 | Metadado **autoria** | ✅ | `dc.contributor.author`, após coalescência |
| 5 | Metadado **ano** | ✅ | `dc.date.issued`, com recurso declarado a `dc.date.accessioned` |
| 5 | Metadado **contexto** | ❌ | Sem campo e sem derivação; o resumo não é situação de produção (§2.2). Só por coleção |
| 5 | Metadado **tipo** | ⚠️ | Mapeado de `dc.type`, vocabulário provavelmente mais estreito (§2.3) |
| 5 | Metadado **nível de confiabilidade** | ⚠️ | Só por estrato, nunca por documento (§2.4) |
| 5 | Metadado **restrição de uso** | ⚠️ ou ✅ | Depende do vocabulário de `dc.rights` (§2.1) |
| 5 | Problematizar antes de responder | ✅ | Não depende de metadado. Já implementado (`sessao.py`) |
| 5 | Explicitar fonte e autoria, com referência verificável | ✅ **melhora** | Autoria existe; o handle dá URL permanente que o usuário pode abrir |
| 5 | Assumir posição e mostrar a disputa | ⚠️ | O sistema não sabe de onde cada documento fala (§2.2). Tende ao "freirês" retórico que o PDF (p. 6) chama de risco principal |
| 5 | Recusar o produto acabado | ✅ | Formato de saída, definido no marco |
| 6 | Camada 3 — RAG com citação de fonte | ✅ | Implementado |
| 6 | Camada 3 — marco pedagógico em linguagem natural | ✅ | Implementado (`marcos/*.md`) |
| 6 | Camada 4 — 80 a 150 casos-teste | ✅ **melhora** | O gabarito passa a referenciar o handle em vez do título, que se repete |
| 7 | Rota A — GPU alugada com acervo público | ⚠️ | Exige partição público/restrito confiável: §2.1, ou política por coleção |
| 7 | Rota B — servidor próprio | ✅ | Não depende de metadado |
| 8 | Verificação de direitos documento a documento, registrada | ❌ | Sem os campos (§2.5). Substituível só por declaração institucional por coleção |
| 8 | Anonimização conforme a LGPD | ❌ | Sem triagem e sem registro; o dado está no texto (§2.6) |
| 8 | Catalogação com metadados padronizados | ⚠️ | Vira **normalização** de um catálogo existente, no padrão do acervo |
| 9 | Refinamento do marco com base na avaliação | ✅ | Não depende de metadado |
| 9 | Publicação sob licença aberta (Fase 5) | ⚠️ | Depende de `dc.rights` distinguir licença de nível de acesso |
| 10 | Decisão 3 — lista negativa de dados | ⚠️ | Continua necessária; define escopo em vez de triagem por documento (§2.6) |
| 10 | Risco: substituir a escuta territorial | ✅ **melhora** | `dc.coverage.spatial` permite ancoragem territorial não prevista |

### 3.2 Documentos de fase e esquema v0

| Origem | Funcionalidade | | Motivo |
|---|---|---|---|
| `fase-1` §4.2 | OCR com ferramenta e versão registradas | ⚠️ | Só para o que nós OCRizarmos (§2.8) |
| `fase-1` §4.3 | Extração preservando páginas e seções | ✅ | Vem do PDF |
| `fase-1` §4.5 | Filtro de dados pessoais na ingestão | ❌ | §2.6 |
| `fase-1` §4.6 | Chunking sensível à estrutura, por tipo | ⚠️ | Menos tipos que o previsto; provavelmente mais simples (§2.3) |
| `fase-1` §4.7 | Proveniência por chunk: documento, página, offset | ✅ | Caminho A1, já planejado |
| `fase-1` §4.8 | `versao_embedding` por chunk | ✅ | Não depende do acervo |
| `fase-1` §4.8 | Camada canônica separada do índice | ✅ | Nosso pipeline |
| `fase-1` §4.8 | Reindexação incremental por documento | ✅ | Já implementado (retomada por `uuid5`) |
| `fase-1` §5 | Backups separados de corpus e índice | ✅ | |
| `fase-1` §7 | Os seis metadados obrigatórios em todo documento | ❌ | Dois dos seis não existem por documento |
| `fase-1` §7 | Direitos verificados e registrados em todo documento | ❌ | §2.5 |
| `fase-1` §7 | Nenhum vedado no índice | ⚠️ | O mecanismo é viável; o dado depende de §2.1 |
| `fase-1` §7 | Documento, página e offset recuperáveis em cada chunk | ✅ | |
| `fase-1` §7 | Conjunto público autorizado para GPU alugada | ⚠️ | §2.1 |
| `fase-2` §4.4 | Filtro de restrição dentro da query | ✅ | Mecanismo independe do acervo (esquema §7.4, itens 1 e 2) |
| `fase-2` §4.4 | Busca léxica e `idioma_do_acervo` | ✅ | `dc.language.iso` existe. `dc.subject[en/es/fr]` indica acervo multilíngue, o que **aumenta** o valor da mediação tradutora (90% contra 85% de recall, medido) |
| `fase-3` §7 | `recall@k` contra gabarito | ✅ **melhora** | O handle resolve os títulos repetidos |
| `fase-3` §5 | Rubrica humana de qualidade | ✅ | |
| esquema v0 §6.1 | Payload herda título, autoria, ano, restrição | ⚠️ | Três plenos; o quarto conforme §2.1. Acrescentar o handle, para citação clicável |
| esquema v0 §12 | Rastrear do trecho até a caixa do original | ❌ **substituído** | Sem localização física; o handle rastreia até a página pública do item |

### 3.3 Funcionalidades que o acervo habilita e o plano não previa

| Funcionalidade | Base |
|---|---|
| **Filtro e diversificação territorial** — uma resposta sobre um município traz material daquele território | `dc.coverage.spatial` |
| **Citação com link permanente** que o usuário abre e confere | `dc.identifier.uri` |
| **Reforço léxico por assunto** na busca BM25 | `dc.subject` — rejeitado no esquema v0 §9 por custo de preenchimento que agora é zero |
| **Faceta por coleção e série** na exploração | `collection`, `dc.relation.ispartofseries` |

---

## 4. A saída estrutural: política por coleção

A regra que resolve a maioria dos casos ⚠️:

> **O que não pode ser preenchido por documento pode ser declarado por coleção.**

`collection` existe, tem cardinalidade pequena (dezenas, não milhares) e agrupa material de
origem homogênea. Uma tabela versionada no repositório — `metadados/politica_por_colecao.csv` —
resolve de uma vez:

| O quê | Como |
|---|---|
| Restrição de uso | uma decisão por coleção. Coleção fora da tabela não entra no índice — a falha fechada se mantém |
| Contexto | uma a três frases de situação de produção, herdadas pelos itens |
| Confiabilidade | peso do estrato |
| Direitos | a declaração institucional de §2.5, com fundamento, assinatura e data |
| Dados pessoais | o tratamento da coleção: não se aplica, triagem automática, ou fora do escopo |
| Tipo e idioma padrão | recurso quando `dc.type` ou `dc.language.iso` faltarem ou forem ambíguos |

Isso **não é preencher metadado manualmente**: o acervo não é tocado. É uma tabela de política do
lado do projeto, e o trabalho humano cai de uma decisão por documento para uma por coleção.

A forma detalhada está no [esquema v0.2](esquema-de-metadados.md), §5.

---

## 5. O que continua intacto

Tudo o que depende do nosso pipeline e não do catálogo: página, offset e seção por chunk;
`versao_embedding`; camada canônica; reindexação incremental; filtro dentro da query; mediação;
sessão dialógica; harness de avaliação. Nada disso muda com esta análise.

---

## 6. Resumo para decisão

**Três requisitos do PDF oficial não são implementáveis a partir destes metadados:**

1. **Contexto de produção por documento** (p. 5). Com ele enfraquece "assumir posição e mostrar a
   disputa" — o diferencial que o próprio PDF chama de "o argumento mais forte diante de
   financiadores". Mitigável por coleção, não por documento.
2. **Verificação de direitos documento a documento, registrada** (p. 8). Substituível por
   declaração institucional por coleção — **decisão da direção**.
3. **Anonimização de dados pessoais antes de indexar** (p. 8). Substituível apenas por restrição
   de escopo e triagem automática que bloqueia, o que é menos do que a LGPD e `fase-1` §4.5 pedem —
   **decisão da direção**, com o risco registrado.

**Dois ficam degradados:** confiabilidade (por estrato) e tipo (vocabulário mais estreito, o que
barateia o chunking).

**Um é condicional**, e se resolve com uma contagem de valores: restrição de uso.

**Três ganhos não previstos:** território, citação por URL permanente, assunto controlado — o
primeiro atacando o risco que o PDF identifica como principal.

### Decisões que este documento pede

| Decisão | De quem | Bloqueia |
|---|---|---|
| Aceitar o depósito no repositório como evidência de direitos, por coleção | Direção | Toda indexação |
| Tratamento de dados pessoais: escopo, triagem automática, risco aceito | Direção + comitê | Toda indexação |
| Quais coleções entram, e com que restrição | Direção + curadoria | Toda indexação |
| Contexto de produção de cada coleção | Curadoria | Qualidade da resposta, não a indexação |
| Peso dos estratos para confiabilidade | Comitê | Nada — entra como `nao_avaliada` |
