# Esquema de metadados do acervo

> [Índice dos documentos](../README.md) · [Limites dos metadados do acervo](limites-dos-metadados-do-acervo.md) · [Fase 1 — Corpus](../plano/fase-1-corpus.md) · [Arquitetura](../engenharia/arquitetura.md) §9

**Versão do esquema:** 0.2 — **proposta, não aprovada**
**Data:** 2026-09-21
**Autoria desta redação:** equipe técnica
**Aprovação necessária:** direção (direitos e dados pessoais, §5.4 e §5.5), comitê pedagógico
(confiabilidade e contexto, §5.2 e §5.3) e curadoria do Centro de Referência (política por
coleção, §5)

> Enquanto a versão for 0.x, este esquema **não deve ser usado para indexar o acervo**. Ele está
> escrito para ser lido, discutido e emendado. A versão 1 é a que trava.

---

## 0. O que mudou na versão 0.2, e por quê

A versão 0 partia de uma premissa que não se confirmou: que o acervo seria **catalogado** para
este projeto, documento a documento, por uma curadoria preenchendo os campos que o sistema
precisa.

O acervo, na verdade, é um **repositório DSpace já catalogado**, com metadados Dublin Core, e
fomos informados de que esses metadados **não serão modificados nem preenchidos manualmente**. A
análise completa — o que o acervo tem, o que falta, e que funcionalidades documentadas ficam de
pé — está em [limites-dos-metadados-do-acervo.md](limites-dos-metadados-do-acervo.md).

O que isso muda neste esquema:

| Na versão 0 | Na versão 0.2 |
|---|---|
| Camada 1 preenchida por pessoa, por documento | Camada 1 **derivada** do acervo, somente leitura |
| 21 campos obrigatórios de catalogação | 17 campos obrigatórios, **todos derivados** (§4) |
| Decisões humanas por documento | Decisões humanas **por coleção** (§5) — dezenas, não milhares |
| `metadados/catalogo.csv` editável em planilha | Exportação do DSpace, somente leitura, e `metadados/politica_por_colecao.csv` editável |
| Identificador emitido pela curadoria (`ipf-000123`) | Handle do repositório, normalizado (§4.1) |
| Mapa Dublin Core para **exportar** na Fase 5 | Mapa DSpace para **importar** — é a ingestão (§9) |
| `contexto`, `confiabilidade`, direitos e anonimização por documento | Por coleção. Por documento, não existem |

**Três requisitos do PDF oficial deixam de ser atendíveis por documento** — contexto de produção,
registro de verificação de direitos e anonimização antes de indexar. A política por coleção
atenua os três e não substitui nenhum; as decisões que isso exige estão em §11.

---

## 1. O que este documento é

O esquema de metadados do acervo do Centro de Referência Paulo Freire: **que informações o
sistema usa sobre cada documento, de onde cada uma vem, quem decide o que não vem do acervo, e o
que o sistema faz com cada uma**.

[fase-1-corpus.md](../plano/fase-1-corpus.md) classifica o esquema como **a trava cara do projeto** (§2 e §8), porque
refazê-lo significava reprocessar o acervo à mão. Com o acervo somente leitura, a trava muda de
lugar: o que custa caro agora é **errar uma regra de derivação** que já produziu o índice, e
**decidir mal uma política de coleção** que já valeu para centenas de documentos.

**A quem se dirige.**

| Se você é | Leia | Pode pular |
|---|---|---|
| Direção | §0, §5.1, §5.4, §5.5 e §11 | §4, §7 a §9 |
| Comitê pedagógico | §0, §5.2, §5.3 e §11 | §7 a §9 |
| Curadoria | §0, §5 inteiro, §11 | §7 e §8 |
| Equipe técnica | tudo, com atenção a §3, §4, §8 e §9 | |

**O que este documento não faz.** Não define a lista negativa de dados pessoais (Fase 0,
decisão 3), não define a escala de confiabilidade (comitê, §11.6) e não implementa nada.

---

## 2. Sete princípios, e por que cada um

Os mesmos sete da versão 0, reescritos para um acervo que não se altera. Onde o princípio mudou,
a razão está dita.

**1. Trabalho humano é por coleção, nunca por documento.** *(Era: "campo obrigatório é custo,
multiplicado pelo tamanho do acervo".)* O acordo de não preencher manualmente elimina o custo
por documento — e com ele a possibilidade de qualquer campo que só uma pessoa lendo o documento
saberia preencher. O que o sistema precisa e o acervo não dá é decidido uma vez por coleção
(§5). Campo que exigiria decisão por documento não existe neste esquema.

**2. Derivado do acervo ≠ declarado pelo projeto.** *(Era: "declarado ≠ derivado".)* Tudo o que
vem do DSpace é derivado, por regra escrita, e **nunca é corrigido à mão** — corrigir à mão
recria a planilha paralela que diverge na primeira reexportação. O que o projeto declara fica em
dois arquivos pequenos e versionados: a política por coleção (§5) e a lista de bloqueios (§8.2).

**3. Ausência se resolve por regra declarada, nunca por célula em branco nem por palpite.** Cada
campo obrigatório tem uma cadeia de origem (§9.2) — coluna preferida, colunas de recurso, valor
padrão da coleção, valor explícito de ausência. Se a cadeia inteira falha, **o documento não
entra no índice**, e a validação diz por quê.

**4. Falha fechada em restrição de uso — e só se restringe, nunca se libera.** Documento sem
restrição resolvida é tratado como `vedado`. O filtro da busca é por **lista de permitidos**
(§8.3). E toda fonte de restrição — coleção, `dc.rights`, bloqueio — só pode tornar o documento
**mais** restrito: prevalece a mais restritiva (§4.4).

**5. Vocabulário controlado por mapeamento fechado.** O vocabulário do acervo não é o nosso
(`dc.type` traz "Dissertação", não `academico`). A tradução é uma tabela fechada, versionada. Valor
do acervo **ausente da tabela não cai num valor genérico**: o documento não entra até que a tabela
seja completada. É o que impede um "Outro" de virar `obra` em silêncio.

**6. O esquema e a derivação se versionam junto com o dado.** Cada registro grava sob que versão
do esquema (`esquema_versao`) **e sob que versão das regras de derivação** (`versao_da_derivacao`)
foi produzido. A segunda é nova: quando o mapeamento `dc.type → tipo` mudar, é ela que diz quais
pontos do índice foram produzidos pela regra antiga.

**7. Registro de quem decidiu e quando.** *(Era: nos pontos de catalogação.)* Não há mais
catalogação a assinar. Assinam-se as decisões que o projeto toma: cada linha da política por
coleção e cada bloqueio carregam autoria e data. [fase-1-corpus.md](../plano/fase-1-corpus.md) §6 exige registro para
auditoria, e auditoria sem autoria e data não é auditoria.

---

## 3. O custo do erro não é o mesmo em todo campo

| Nível | O que erra | Custo de corrigir depois | Campos |
|---|---|---|---|
| **1 — irreversível na prática** | O identificador do documento | **Reindexação do documento.** O `chunk_id` é `"{arquivo}::{índice}"` e o ID do ponto é `uuid5(chunk_id)` | `id` |
| **2 — reindexação** | O texto extraído, o recorte, o embedding, **o mapeamento de tipo** | **Reindexação** dos documentos afetados | `arquivo_canonico`, `tipo` (a regra, não o valor), `origem_do_texto` quando implica reprocessar OCR |
| **3 — reescrita de payload** | O que viaja no payload do chunk | **Minutos.** Passada sobre os pontos, sem recalcular vetor | `titulo`, `uri`, `autoria`, `ano`, `restricao_uso` |
| **4 — rederivação** | Tudo o que não vai ao índice | **Segundos.** Rodar a derivação de novo | o resto |

O que mudou em relação à versão 0:

- **O identificador deixou de ser decisão nossa.** É o handle, emitido pelo repositório. O risco
  migra para fora do projeto: uma migração do DSpace que reatribua handles quebra o vínculo de
  todo o índice. Por isso se guarda também o identificador interno do DSpace (`uuid_dspace`,
  §4) — não como chave, mas para **detectar** a quebra entre duas exportações.
- **Erro de catalogação no acervo não tem conserto na origem.** Autor mal grafado ou data errada
  no DSpace ficam como estão, porque o acervo não será modificado. Só se corrigem se o próprio
  repositório corrigir e reexportar — e então custam o nível da tabela acima.
- **O nível 2 passou a incluir uma regra, não um valor.** Errar o `tipo` de um documento não
  existe mais como erro humano; errar **uma linha do mapeamento** reindexa todos os documentos
  daquele valor de `dc.type` de uma vez.

> **Regra que sai daí:** a discussão deste esquema gasta o tempo em três coisas — a tabela de
> mapeamento de tipo, a política de cada coleção e o tratamento de dados pessoais. O resto é
> derivação corrigível.

---

## 4. Camada 1a — metadados por documento, derivados do acervo

**Nenhum campo desta camada é digitado.** Todos vêm do CSV do DSpace ou do processamento do
arquivo, por regra escrita em §9. A camada inteira é **regerável** a partir da exportação, da
política por coleção e da lista de bloqueios.

**Legenda:** **O** obrigatório — se a derivação não produzir valor, o documento não entra ·
**C** condicional · **op** opcional.

### Tabela geral

| # | Campo | Obr. | Origem (§9 detalha) | Vai ao índice? |
|---|---|---|---|---|
| 1 | `id` | **O** | `dc.identifier.uri` → handle normalizado (§4.1) | **sim** (dentro do `chunk_id`) |
| 2 | `uri` | **O** | `dc.identifier.uri` → URL do handle | **sim** — citação verificável |
| 3 | `uuid_dspace` | op | `id` | não — só detecção de quebra (§3) |
| 4 | `titulo` | **O** | `dc.title` coalescido | **sim** |
| 5 | `titulo_alternativo` | op | `dc.title.alternative` | não |
| 6 | `autoria` | **O** | `dc.contributor.author` coalescido; ausente → `[autoria não identificada]` | **sim** |
| 7 | `autoria_secundaria` | op | `dc.contributor.other[]` | não |
| 8 | `ano` | **O** | `dc.date.issued`; ausente → `dc.date.accessioned` | **sim** |
| 9 | `precisao_da_data` | **O** | `informada` (veio de `issued`) / `desconhecida` (veio de `accessioned`) | não |
| 10 | `data_completa` | op | `dc.date.issued`, quando traz o dia | não |
| 11 | `idioma` | **O** | `dc.language.iso` normalizado; ausente → `idioma_padrao` da coleção | não |
| 12 | `tipo` | **O** | mapeamento fechado de `dc.type` (§4.3); ausente → `tipo_padrao` da coleção | não |
| 13 | `colecao` | **O** | `collection` | não |
| 14 | `restricao_uso` | **O** | o mais restritivo entre coleção, `dc.rights` mapeado e bloqueio (§4.4) | **sim** |
| 15 | `resumo` | op | `dc.description.abstract` coalescido | não |
| 16 | `nota` | op | `dc.description` coalescido | não |
| 17 | `assuntos` | op | `dc.subject` e `dc.subject.other`, todas as variantes | não |
| 18 | `cobertura_espacial` | op | `dc.coverage.spatial` coalescido | não — herdaria para filtro territorial (§7.1) |
| 19 | `publicacao` | op | `dc.publisher` coalescido | não |
| 20 | `serie` | op | `dc.relation.ispartofseries` coalescido | não |
| 21 | `identificador_externo` | op | `dc.identifier.isbn`, `.issn`, `.other` | não |
| 22 | `nivel` | op | `dc.identifier.level[]` — semântica a confirmar (§11.1) | não |
| 23 | `citacao_formatada` | op | `dc.identifier.citation` coalescido | não — exibição |
| 24 | `depositado_em` | op | `dc.date.accessioned` | não |
| 25 | `origem_do_texto` | **O** | pipeline: `digital_nativo` (PDF com texto) / `ocr` (nós rodamos) | não |
| 26 | `ocr_ferramenta` | C | pipeline — em `ocr` | não |
| 27 | `ocr_versao` | C | pipeline — em `ocr` | não |
| 28 | `total_de_paginas` | C | pipeline — se paginado | não |
| 29 | `triagem_automatica` | **O** | pipeline: `limpo` / `bloqueado` / `nao_se_aplica` (§5.5) | não |
| 30 | `arquivo_canonico` | **O** | pipeline | **sim** (é o `documento_origem`) |
| 31 | `hash_do_texto` | **O** | pipeline — sha256 do arquivo canônico | não |
| 32 | `esquema_versao` | **O** | pipeline | não |
| 33 | `versao_da_derivacao` | **O** | pipeline — versão das tabelas de §9 | não |
| 34 | `origem_dos_valores` | **O** | pipeline — de que coluna veio cada campo coalescido | não |

**Dezessete campos obrigatórios, nenhum com custo humano por documento.** Dez vêm do acervo
(com recurso à política por coleção quando a coluna falta) e sete do pipeline.

### 4.1 `id` — o identificador do documento

**Continua o campo mais caro de errar.** O que muda é quem o emite.

| | |
|---|---|
| **Origem** | O handle em `dc.identifier.uri` — o identificador persistente que o DSpace atribui e publica |
| **Forma normalizada** | `hdl-{prefixo}-{sufixo}` — `http://hdl.handle.net/123456789/4567` vira `hdl-123456789-4567` |
| **Arquivo canônico** | `data/corpus_ipf/hdl-123456789-4567.md` — o nome do arquivo é o identificador, como na v0 |
| **Sem handle** | O documento não entra. Não se inventa identificador |

**Por que o handle e não a coluna `id`.** A coluna `id` da exportação é o identificador interno
do DSpace: inteiro até a versão 5, UUID a partir da 6, e reemitido numa migração entre as duas. O
handle é o que o repositório se compromete a manter e o que é publicado para citação. O
identificador interno se guarda em `uuid_dspace` só para comparar exportações: se o mesmo
`uuid_dspace` aparecer com outro handle, ou o mesmo handle com outro `uuid_dspace`, a derivação
para e avisa.

**`dc.identifier.uri` pode trazer mais de um valor** (handle e DOI, por exemplo). Vale o que casa
com o prefixo de handle do repositório; os demais vão para `identificador_externo`.

**A razão da versão 0 continua valendo:** o identificador é opaco, e a legibilidade não faz
falta, porque a citação exibida usa o título — `[Fonte 3: Pedagogia do Oprimido]`, montada em
`etapas/geracao.py` a partir de `titulo_pagina` — e agora pode trazer também o link.

### 4.2 Identificação bibliográfica — `titulo`, `autoria`, `ano`, `idioma`

Os quatro existem no acervo, fragmentados por qualificador de idioma. A regra de coalescência
está em §9.1.

- **`titulo`** — como está no acervo. Título ausente não ocorre em DSpace (o campo é exigido no
  depósito); se ocorrer, o documento não entra.
- **`autoria`** — lista, na forma em que está no acervo. A forma `Sobrenome, Nome` da versão 0
  não é garantida e **não é imposta**: normalizar nomes de pessoa por regra erra mais do que
  acerta. Ausente → `[autoria não identificada]`, que é valor explícito, não branco.
- **`ano`** — quatro dígitos extraídos de `dc.date.issued`. Ausente → ano de
  `dc.date.accessioned`, e `precisao_da_data: desconhecida`.
- **`precisao_da_data`** — **perdeu um valor.** A versão 0 distinguia `exata` de `aproximada`;
  nada no acervo diz se "1968" foi lido na folha de rosto ou estimado. Ficam `informada` e
  `desconhecida`.
- **`idioma`** — ISO 639-1. O acervo pode trazer `pt`, `por` ou `pt_BR`; todos viram `pt`.
  Continua não indo ao payload: a decisão que ele governa (traduzir a consulta, ligar a busca
  léxica) é do acervo inteiro. Mas `dc.subject[en]`, `[es]` e `[fr]` sugerem um acervo
  multilíngue — se a contagem de §11.1 confirmar, `idioma` passa a herdar para o chunk.

> **Título não é identificador** — continua valendo. O gabarito de avaliação deve referenciar
> `id`, não título.

### 4.3 `tipo` — mapeamento fechado

O vocabulário continua o da versão 0 e da `fase-1` §4.6:

| Valor | Estratégia de chunking |
|---|---|
| `obra` | Por seção argumentativa |
| `relatorio` | Por seção do relatório |
| `normativo` | Por artigo/inciso |
| `academico` | Por seção |
| `memoria` | Por pauta/deliberação |

O que muda é que ele **não é atribuído, é traduzido** de `dc.type`, por uma tabela versionada em
`metadados/mapa_tipo.csv`:

```
dc_type,tipo
Tese,academico
Dissertação,academico
Artigo,academico
Livro,obra
Capítulo de livro,obra
Relatório,relatorio
```

*Os valores acima ilustram a forma; a tabela real sai da contagem de §11.1.*

Três regras:

1. **Valor de `dc.type` ausente da tabela → o documento não entra** (princípio 5), e a validação
   lista os valores sem mapeamento. Não há linha "qualquer outro → obra".
2. `dc.type` vazio → `tipo_padrao` da coleção. Sem padrão na coleção, o documento não entra.
3. **Mudar uma linha da tabela reindexa todos os documentos daquele valor** (§3, nível 2). A
   tabela se fecha antes da primeira indexação.

**Consequência provável:** um repositório de produção publicada tende a ter pouco `memoria` e
`normativo`. Se a contagem confirmar, as estratégias de corte correspondentes ficam sem uso — o
que barateia o chunking, não o quebra.

### 4.4 `restricao_uso` — três fontes, prevalece a mais restritiva

| Valor | Significado operacional |
|---|---|
| `publicavel` | Pode ser recuperado por qualquer usuário **e** pode subir para infraestrutura de terceiros (GPU alugada, Rota A) |
| `interno` | Só no servidor próprio, só para usuário autenticado da instituição |
| `vedado` | **Não é indexado.** Ponto vedado no índice é defeito |

O valor do documento é o **mais restritivo** entre:

1. a `restricao_uso` da coleção (§5.1) — **obrigatória**; coleção sem linha na política não
   entra;
2. `dc.rights` traduzido por `metadados/mapa_direitos.csv`, **se** a contagem de §11.1 mostrar
   que é vocabulário (`Acesso Restrito` → `interno`, `Acesso Embargado` → `vedado`); se for texto
   livre, esta fonte não é usada;
3. a lista de bloqueios (§8.2), que só contém `vedado`.

Ordem: `vedado` > `interno` > `publicavel`. **Nenhuma fonte libera o que outra restringiu.**
Continua valendo tudo o que a versão 0 dizia sobre o filtro — dentro da query, antes do ranking,
por lista de permitidos (§8.3).

### 4.5 Procedência técnica do texto

| Campo | Para quê |
|---|---|
| `origem_do_texto` | `digital_nativo` quando o PDF já tem camada de texto aproveitável; `ocr` quando **nós** rodamos o OCR. Não há como saber como foi gerada a camada de texto de um PDF que chegou pronto — é `digital_nativo` do nosso ponto de vista, e a revisão amostral cobre isso por coleção (§11.9) |
| `ocr_ferramenta`, `ocr_versao` | Exigidos por `fase-1` §4.2. Preenchidos pelo pipeline quando ele roda OCR |
| `total_de_paginas` | Valida a `pagina` de cada chunk. `dc.format.extent` não está na exportação; conta-se do PDF |

> **Qualidade de OCR é teto de qualidade do sistema** (`fase-1` §4.2). Erro de OCR não gera
> exceção: gera citação errada, com aparência perfeita.

### 4.6 Registro do próprio registro

| Campo | Nota |
|---|---|
| `arquivo_canonico` | Texto extraído e normalizado, separado do índice (`fase-1` §4.8) |
| `hash_do_texto` | sha256 do arquivo canônico. Diz, sem depender de ninguém lembrar, que o texto mudou |
| `esquema_versao` | Princípio 6 |
| `versao_da_derivacao` | Versão conjunta de `mapa_tipo.csv`, `mapa_direitos.csv` e das regras de §9. Princípio 6 |
| `origem_dos_valores` | Para cada campo coalescido, a coluna de onde veio: `{"autoria": "dc.contributor.author[pt_BR]", ...}`. É o que torna um conflito entre colunas investigável |

`catalogado_por`, `catalogado_em`, `revisado_por` e `revisado_em` da versão 0 **saíram**: não há
catalogação neste projeto. `dc.description.provenance` teria quem depositou e quando, mas **não é
lido** — contém o e-mail do depositante (§9.3).

---

## 5. Camada 1b — política por coleção

O que o sistema precisa, o acervo não dá e ninguém vai preencher por documento é **decidido uma
vez por coleção**, em `metadados/politica_por_colecao.csv`. É o único lugar em que o projeto
declara metadado — e é uma tabela de dezenas de linhas, não de milhares.

| Campo | Obr. | Valores | Quem decide |
|---|---|---|---|
| `colecao` | **O** | exatamente como na coluna `collection` — é a chave | — |
| `nome` | op | nome legível | curadoria |
| `restricao_uso` | **O** | `publicavel` / `interno` / `vedado` | direção + curadoria |
| `contexto` | **O** | texto, 1–3 frases | curadoria |
| `confiabilidade` | **O** | escala do comitê; até lá, `nao_avaliada` | comitê |
| `direitos_situacao` | **O** | `deposito_autorizado` / `dominio_publico` / `licenciado` / `nao_verificado` / `negado` | direção |
| `direitos_fundamento` | C | texto — obrigatório fora de `nao_verificado` e `negado` | direção |
| `tratamento_dados_pessoais` | **O** | `nao_se_aplica` / `triagem_automatica` / `fora_do_escopo` | direção + comitê |
| `tipo_padrao` | op | um dos cinco tipos — usado quando `dc.type` vem vazio | curadoria |
| `idioma_padrao` | op | ISO 639-1 — usado quando `dc.language.iso` vem vazio | curadoria |
| `decidido_por` | **O** | texto | — |
| `decidido_em` | **O** | AAAA-MM-DD | — |

**Coleção que não está na tabela não entra no índice.** É a falha fechada aplicada à coleção
inteira: uma coleção nova que apareça numa reexportação fica fora até alguém decidir sobre ela.

### 5.1 `restricao_uso` da coleção

É o piso de restrição de todos os documentos da coleção (§4.4). A fronteira `publicavel` /
`interno` é a partição público/restrito da Fase 0 §3.4 — o que pode subir para GPU alugada.

### 5.2 `contexto` da coleção

Uma a três frases dizendo **de que situação o material da coleção saiu** — quem produziu, para
quem, a serviço de quê. Mesmo critério da versão 0:

- **Bom:** "Dissertações e teses defendidas no programa X sobre educação de jovens e adultos,
  depositadas pelos autores após a defesa."
- **Ruim:** "Produção acadêmica."

**Limite, que precisa estar à vista:** isto é contexto do *gênero*, não do documento. Um
relatório encomendado por uma secretaria e uma crítica publicada sobre a mesma política, se
estiverem na mesma coleção, continuam indistinguíveis. É a perda que a versão 0.2 não recupera, e
ela enfraquece o requisito do PDF oficial (p. 5) de "dizer de onde fala e apresentar as posições
em disputa" — ver [limites-dos-metadados-do-acervo.md](limites-dos-metadados-do-acervo.md) §2.2.

### 5.3 `confiabilidade` da coleção

Vocabulário fechado, definido pelo comitê (§11.6). Enquanto não houver escala, `nao_avaliada`.
Usá-la em ranking continua sendo mudança de comportamento do sistema, sujeita a veto do comitê e
ao harness da Fase 3.

A pergunta ao comitê fica mais fácil do que na versão 0: não é "que nota cada documento merece",
é "que peso relativo têm os estratos que o acervo já distingue". Se `nivel` (§4, campo 22) for
nível acadêmico, a escala pode combinar coleção e nível.

### 5.4 Direitos — declaração por coleção

A versão 0 pedia titular, evidência, quem verificou e quando, **por documento** — o que `fase-1`
§6 chama de "registro de verificação de direitos, documento a documento". O acervo não tem nada
disso, e não será preenchido.

O substituto é uma **declaração institucional por coleção**:

- `deposito_autorizado` — o depósito no repositório institucional é tomado como evidência de
  autorização de uso. `direitos_fundamento` diz em que se apoia (termo de depósito, política do
  repositório).
- `dominio_publico`, `licenciado` — como na versão 0, declarados para a coleção inteira.
- `nao_verificado`, `negado` — **não entram no índice** (trava mantida da versão 0).

**Isto é menos do que a Fase 1 pede**, e a decisão de aceitar é da direção (§11.3). É defensável
para produção própria de acesso aberto; não é para material de terceiros depositado sem licença.

### 5.5 Dados pessoais — tratamento por coleção e triagem automática

A versão 0 pedia triagem e anonimização por documento, com registro auditável. O dado pessoal
está no corpo do texto, e nenhum campo do acervo o registra. **Anonimização antes de indexar
(`fase-1` §4.5) não é implementável sob o acordo de não intervir documento a documento.**

O que a versão 0.2 oferece:

| `tratamento_dados_pessoais` | Efeito |
|---|---|
| `nao_se_aplica` | Coleção de obras publicadas, normativos: não há triagem. `triagem_automatica` do documento é `nao_se_aplica` |
| `triagem_automatica` | Cada documento passa por detecção automática no texto canônico (CPF, e-mail, telefone, endereço e o que a lista negativa permitir operacionalizar). Achado → `triagem_automatica: bloqueado` e **o documento não entra**. Não anonimiza: bloqueia |
| `fora_do_escopo` | A coleção inteira não entra. Implica `restricao_uso: vedado` — a validação rejeita a linha que diga outra coisa |

**O que a triagem automática não pega** — relatos, deliberações sigilosas, dados de saúde em
texto corrido — é justamente o que a lista negativa do PDF (p. 10, decisão 3) mais cita. Por isso
coleção com esse tipo de material deve ser `fora_do_escopo`, não `triagem_automatica`. A decisão
é da direção e do comitê (§11.4).

Documento bloqueado pela triagem entra em relatório para revisão humana, que pode confirmá-lo na
lista de bloqueios (§8.2) ou — não há terceira via — deixá-lo bloqueado.

---

## 6. Um registro completo

Os valores são ilustrativos; a forma é a real.

**Linha da política** (`metadados/politica_por_colecao.csv`):

```csv
colecao,nome,restricao_uso,contexto,confiabilidade,direitos_situacao,direitos_fundamento,tratamento_dados_pessoais,tipo_padrao,idioma_padrao,decidido_por,decidido_em
"123456789/100","Teses e dissertações","publicavel","Teses e dissertações sobre educação de jovens e adultos, depositadas pelos autores após a defesa.","nao_avaliada","deposito_autorizado","Termo de depósito do repositório, cláusula de acesso aberto","nao_se_aplica","academico","pt","direção/IPF","2026-10-02"
```

**Registro derivado de um item**:

```json
{
  "id": "hdl-123456789-4567",
  "uri": "http://hdl.handle.net/123456789/4567",
  "uuid_dspace": "3f2a9c1e-8b4d-4e7a-9f10-2c6d5e8a7b31",
  "titulo": "Alfabetização de jovens e adultos no município de Osasco",
  "autoria": ["Silva, Maria de Lourdes"],
  "ano": "2014",
  "precisao_da_data": "informada",
  "data_completa": "2014-11-20",
  "idioma": "pt",
  "tipo": "academico",
  "colecao": "123456789/100",
  "restricao_uso": "publicavel",
  "assuntos": ["Educação de jovens e adultos", "Alfabetização", "Adult education"],
  "cobertura_espacial": ["Osasco (SP)"],
  "nivel": "Mestrado",
  "origem_do_texto": "digital_nativo",
  "total_de_paginas": 148,
  "triagem_automatica": "nao_se_aplica",
  "arquivo_canonico": "data/corpus_ipf/hdl-123456789-4567.md",
  "hash_do_texto": "9b1c…",
  "esquema_versao": "0.2",
  "versao_da_derivacao": 1,
  "origem_dos_valores": {
    "titulo": "dc.title",
    "autoria": "dc.contributor.author[pt_BR]",
    "ano": "dc.date.issued",
    "tipo": "dc.type[pt_BR] → mapa_tipo.csv",
    "restricao_uso": "politica_por_colecao"
  }
}
```

Repare no que o registro não tem: `contexto`, `confiabilidade` e direitos não estão nele. São da
coleção, e se consultam por `colecao`.

---

## 7. Camada 2 — metadados por chunk

**Nenhum campo desta camada é digitado.** Todos são herdados do registro derivado ou calculados
pelo corte e pela indexação. Os campos existem em `src/rag/modelos.py`, classe `Chunk`.

| Campo do `Chunk` | Origem | Preenchido por | Estado hoje |
|---|---|---|---|
| `chunk_id` | `"{arquivo_canonico}::{índice}"` | chunking | ✅ |
| `texto` | o trecho | chunking | ✅ |
| `documento_origem` | nome do arquivo canônico (= `id` + extensão) | chunking | ✅ |
| `titulo_pagina` | `titulo` | chunking, do registro | ✅ (do cabeçalho do `.txt`) |
| `chunk_index` | posição no documento | chunking | ✅ |
| `pagina` | página do original onde o trecho começa | corte sensível à estrutura | ⬜ vazio |
| `secao` | caminho da seção | corte sensível à estrutura | ⬜ vazio |
| `inicio`, `fim` | offset em caracteres | corte sensível à estrutura | ⬜ vazio |
| `versao_embedding` | modelo que gerou o vetor | **indexação** | ⬜ vazio |
| `restricao_uso` | herdado | chunking, do registro | ⬜ vazio — e com a semântica errada (§8.3) |
| `uri` | herdado | chunking, do registro | ➕ a acrescentar |
| `autoria` | herdado | chunking, do registro | ➕ a acrescentar |
| `ano` | herdado | chunking, do registro | ➕ a acrescentar |

### 7.1 O que herda, e por que só isso

O banco vetorial **não faz junção**: filtro e citação só enxergam o payload do próprio ponto.
Herda o que participa de filtro ou aparece na citação; o resto fica no registro derivado.

| Herda | Por quê |
|---|---|
| `titulo` → `titulo_pagina` | a citação exibida é `[Fonte N: título]` |
| `restricao_uso` | filtro dentro da query |
| `id` → dentro de `documento_origem` e `chunk_id` | chave para voltar ao registro |
| `uri` *(novo)* | a citação vira link que o usuário abre e confere — o que "referência verificável" (PDF p. 5) passa a significar |
| `autoria`, `ano` | a diretriz do marco exige explicitar autoria junto da fonte |

Casos de fronteira:

- **`confiabilidade`** herdaria no dia em que for usada como filtro ou ponderação. Acrescentar ao
  payload depois é nível 3.
- **`idioma`** herdaria se o acervo for substancialmente multilíngue (§4.2).
- **`tipo`** herdaria se o sistema passar a diversificar por tipo de documento.
- **`cobertura_espacial`** *(novo)* herdaria no dia em que houver filtro ou diversificação
  territorial — a funcionalidade que o acervo habilita e o plano não previa, e que ataca o risco
  que o PDF (p. 6) chama de principal: resposta sem ancoragem no território concreto.

### 7.2 Duas coisas que ninguém preenche hoje

Sem mudança em relação à versão 0: **`versao_embedding`** só pode ser preenchida no caminho
`JSONL → payload`, pela indexação; e **`pagina`, `secao`, `inicio` e `fim`** dependem do corte
sensível à estrutura (caminho A1 do [roadmap](../roadmap.md#os-caminhos-de-recorte-que-ficam-para-essa-janela)). Nenhum dos dois
depende do acervo — vêm do arquivo, não do catálogo.

---

## 8. Camada 3 — contrato técnico

### 8.1 Forma dos nomes e dos valores

| Regra | Valor |
|---|---|
| Nomes de campo | português do Brasil, `snake_case`, sem acento |
| Valores de vocabulário do projeto | minúsculas, sem acento, `_` no lugar do espaço |
| Valores vindos do acervo | **como estão**, exceto onde §9 manda normalizar (handle, idioma, ano) |
| Datas | `AAAA-MM-DD`; `ano` isolado é `AAAA` |
| Idioma | ISO 639-1, duas letras |
| Multivalorado no CSV do DSpace | separador **`||`** (e não `;`, como dizia a versão 0) |
| Ausência | valor explícito ou documento fora — nunca célula vazia no registro derivado |

### 8.2 Onde cada coisa vive

```
metadados/exportacao/AAAA-MM-DD.csv   ← exportação do DSpace. SOMENTE LEITURA — nunca editada.
                                        Cada reexportação é um arquivo novo
metadados/politica_por_colecao.csv    ← §5. Editável, versionado. É onde o projeto decide
metadados/mapa_tipo.csv               ← §4.3. dc.type → tipo
metadados/mapa_direitos.csv           ← §4.4. dc.rights → restricao_uso, se for vocabulário
metadados/bloqueios.csv               ← id, motivo, bloqueado_por, bloqueado_em. Só `vedado`
data/corpus_ipf/hdl-*.md              ← camada canônica. O nome do arquivo é o identificador
data/catalogo.jsonl                   ← camada 1a derivada, uma linha por documento. Regerável
data/chunks.jsonl                     ← camada 2
coleção corpus_ipf (Qdrant)           ← payload de cada ponto = Chunk.como_dicionario()
```

**`bloqueios.csv` é a única entrada por documento, e só serve para restringir.** Um documento
com dado pessoal descoberto depois, um pedido de retirada, um direito contestado: precisa haver
como vedar um documento sem esperar decisão sobre a coleção inteira. Não é preenchimento de
metadado — não existe forma de *liberar* por esta lista, nem de corrigir campo.

**Como o pipeline lê.** A derivação é uma etapa própria (`etapas/catalogo.py`), que lê a
exportação, as tabelas de `metadados/` e o texto canônico, e escreve `data/catalogo.jsonl`. O
chunking lê esse artefato. As etapas continuam se comunicando por arquivo em disco, sem importar
umas às outras — a regra estrutural do repositório não muda.

### 8.3 O filtro de restrição de uso — por inclusão, nunca por exclusão

Sem mudança em relação à versão 0:

```
# certo — falha fechada
filtro: restricao_uso ∈ {"publicavel"}            # servidor público
filtro: restricao_uso ∈ {"publicavel", "interno"} # servidor próprio, usuário autenticado

# errado — falha aberta
filtro: restricao_uso ≠ "vedado"
```

Com filtro por exclusão, um ponto sem `restricao_uso` no payload é recuperado. Com filtro por
inclusão, não casa com nada e fica de fora — o erro vira ausência de resultado, que alguém
percebe, em vez de vazamento, que ninguém percebe.

> **Consequência para o código atual:** `src/rag/modelos.py` documenta
> `restricao_uso: str = ""  # vazio = público`. É a semântica oposta, inofensiva enquanto o corpus
> é o da UESP, e precisa mudar **antes** de o primeiro documento do IPF ser indexado.

### 8.4 O que este esquema exige do código, e ainda não existe

| # | Pendência | Toca | Invalida o índice? |
|---|---|---|---|
| 1 | **Filtro na busca.** `RepositorioVetorial.buscar()` recebe filtro; o Qdrant usa `query_filter`; o dublê `RepositorioFalso` acompanha no mesmo commit | `protocolos.py`, `clientes/qdrant.py`, `etapas/recuperacao.py`, `tests/apoio.py` | não |
| 2 | **Índice de payload** em `restricao_uso` | `clientes/qdrant.py` | não |
| 3 | **`pagina` e `uri` no `TrechoRecuperado`**, e o link na citação | `modelos.py`, `clientes/qdrant.py`, `etapas/geracao.py` | não |
| 4 | **Etapa de derivação** — lê a exportação, coalesce (§9.1), normaliza handle e idioma, aplica os mapas, a política e os bloqueios, escreve `data/catalogo.jsonl` | `etapas/catalogo.py` (novo) | não |
| 5 | **Validação dentro da derivação**, que **bloqueia**: sem handle, coleção sem política, `dc.type` sem mapeamento, política incoerente (`fora_do_escopo` sem `vedado`), handle trocado entre exportações | `etapas/catalogo.py` | não |
| 6 | **Triagem automática de dados pessoais** sobre o texto canônico, para coleções em `triagem_automatica` | `etapas/catalogo.py` | não |
| 7 | **Chunking lê `data/catalogo.jsonl`** para herdar `titulo`, `uri`, `restricao_uso`, `autoria`, `ano`, e escolher a estratégia por `tipo` | `etapas/chunking.py` | sim (payload de todo chunk) |
| 8 | **`versao_embedding` preenchida na indexação** | `etapas/indexacao.py` | sim (payload) |
| 9 | **Semântica de `restricao_uso` vazia** invertida (§8.3) | `modelos.py` | não |
| 10 | **Gabarito de avaliação por `id`**, não por título | `avaliacao/casos.jsonl`, `avaliacao.py` | não |

Os itens 7 e 8 mudam o payload, não o vetor — e entram de graça junto da reindexação da troca de
corpus.

---

## 9. Mapa do acervo (DSpace) para o esquema

Na versão 0 esta seção era um mapa para **exportar** em Dublin Core na Fase 5. Agora o acervo já
é Dublin Core, e o mapa corre no sentido contrário: é a ingestão. A exportação da Fase 5 passa a
ser trivial — os campos de origem são os mesmos.

### 9.1 Coalescência por qualificador de idioma

O DSpace grava o mesmo elemento em várias colunas conforme o idioma declarado no depósito. Para
cada campo, vale a **primeira coluna não vazia**, nesta ordem:

```
[pt_BR] → [pt] → sem qualificador → [] → [es] → [en] → [fr]
```

- Campos multivalorados (`autoria`, `assuntos`, `cobertura_espacial`) **unem** as colunas, sem
  repetir valor igual — exceto `autoria`, que usa só a primeira coluna não vazia, para não
  duplicar a mesma pessoa grafada de dois jeitos.
- Dentro de uma célula, valores múltiplos são separados por `||`.
- A coluna usada vai para `origem_dos_valores`.
- Quando duas colunas da mesma cadeia têm valores **diferentes e não vazios** para um campo de
  valor único (`titulo`, `ano`), prevalece a ordem acima e a derivação **registra o conflito** no
  relatório — não bloqueia.

### 9.2 Cadeia de origem de cada campo obrigatório

| Campo | Cadeia |
|---|---|
| `id`, `uri` | `dc.identifier.uri` (valor com o prefixo de handle) → **fora** |
| `titulo` | `dc.title` coalescido → **fora** |
| `autoria` | `dc.contributor.author` coalescido → `[autoria não identificada]` |
| `ano` | `dc.date.issued` coalescido → `dc.date.accessioned` (e `precisao_da_data: desconhecida`) |
| `idioma` | `dc.language.iso` coalescido e normalizado → `idioma_padrao` da coleção → **fora** |
| `tipo` | `mapa_tipo[dc.type coalescido]` → se `dc.type` vazio, `tipo_padrao` da coleção → **fora** |
| `colecao` | `collection` → **fora** |
| `restricao_uso` | mais restritiva de: política da coleção (obrigatória, senão **fora**), `mapa_direitos[dc.rights]` se aplicável, `bloqueios.csv` |

**Fora** significa: o documento não entra no índice e aparece no relatório da derivação, com o
motivo.

### 9.3 Colunas do acervo que não são usadas

| Coluna | Por quê |
|---|---|
| `dc.description.provenance` (todas) | Registro automático do DSpace. **Contém o e-mail de quem depositou** — dado pessoal no próprio catálogo. Não é lida |
| `dc.date.available` | Data de disponibilização no repositório; não diz nada sobre o documento |
| `dc.format.medium[pt_BR]` | Sem uso depois da extração |
| `dc.format.mimetype[pt_BR]` | Só para escolher o extrator — o pipeline lê o tipo do próprio arquivo |
| `dc.rights` | Usada **só** se for vocabulário (§4.4). Texto livre de licença não decide nada automaticamente |

---

## 10. Campos considerados e rejeitados

| Campo | Situação na 0.2 |
|---|---|
| **Resumo** | Era rejeitado por custar 10–20 minutos por documento. **Agora é opcional e derivado** (`resumo`): custo zero. Não entra no texto embutido — a recuperação é sobre o texto integral |
| **Palavras-chave / assunto** | Era rejeitado por custo e por inconsistência sem tesauro. O custo sumiu; a inconsistência fica. **Opcional e derivado** (`assuntos`), para reforço léxico e faceta exploratória — **não para filtro de precisão** |
| **Público-alvo / nível de dificuldade** | Continua rejeitado |
| **Número de chunks do documento** | Continua rejeitado — conta-se do índice |
| **Formato do original, tamanho do arquivo** | Continuam rejeitados |
| **`contexto`, `confiabilidade` por documento** | **Saíram da camada de documento** — não há quem os preencha. Existem por coleção (§5) |
| **`localizacao_do_original`, `estado_do_original`** | **Saíram.** Sem origem no acervo. A rastreabilidade passa a ser até a página pública do item (`uri`), não até a caixa |
| **`direitos_titular`, `direitos_evidencia`, `direitos_verificado_*` por documento** | **Saíram.** Substituídos pela declaração por coleção (§5.4) |
| **`triagem_dados_pessoais`, `anonimizacao_*` por documento** | **Saíram.** Substituídos por tratamento por coleção e triagem automática (§5.5) |
| **`ocr_revisao_amostral` por documento** | **Saiu.** A revisão amostral passa a ser por coleção (§11.9) |
| **`catalogado_*`, `revisado_*`, `lote_de_ingestao`** | **Saíram.** Não há catalogação; o lote é a coleção |

---

## 11. O que falta decidir — e de quem é a decisão

### 11.1 Os valores do acervo — **equipe técnica, antes de tudo**

*Que valores existem, de fato, nas colunas que decidem?*

Esta versão foi escrita a partir dos **nomes** das colunas. Contar os valores de `dc.rights`,
`dc.type`, `collection`, `dc.identifier.level`, `dc.language.iso` e a presença de handle em
`dc.identifier.uri` decide §4.3, §4.4, §5 e o tamanho da política. O comando está em
[limites-dos-metadados-do-acervo.md](limites-dos-metadados-do-acervo.md) §1.1.

### 11.2 Os arquivos vêm junto? — **curadoria + equipe técnica**

*Temos os PDFs de cada item, ou só o catálogo?*

Sem os bitstreams não há corpus. E, se vierem, *em que formato e com que camada de texto* — o que
decide quanto OCR o projeto vai rodar.

### 11.3 Depósito como evidência de direitos — **direção**

*A instituição aceita que o depósito no repositório seja a evidência de autorização de uso, por
coleção, em lugar da verificação documento a documento que a Fase 1 pede?*

Se não aceitar, não há como indexar nada sem intervenção por documento, o que o acordo exclui.

### 11.4 Dados pessoais — **direção + comitê**

*Que coleções ficam fora do escopo, e em quais a triagem automática basta?*

Depende da lista negativa da Fase 0, decisão 3 — que continua sendo pré-requisito, mas deixa de
ser aplicada documento a documento e passa a definir quais coleções entram. **Anonimização antes
de indexar, como `fase-1` §4.5 pede, não é oferecida por esta versão**, e a decisão de seguir
assim precisa estar escrita, com o risco registrado.

### 11.5 Quais coleções entram, e com que restrição — **direção + curadoria**

*Para cada coleção: entra? `publicavel` ou `interno`?* E a pergunta da versão 0 que continua
aberta: quem é "usuário autenticado da instituição", e há mais de um nível de acesso interno?

### 11.6 A escala de `confiabilidade` — **comitê pedagógico**

*Que peso relativo têm os estratos que o acervo já distingue?*

- Quantos níveis, e que **estrato observável** corresponde a cada um (coleção, tipo, nível
  acadêmico).
- O campo **pondera o ranking** ou apenas informa quem lê a resposta? Ponderar é mudança de
  comportamento, sujeita a veto e ao harness da Fase 3.

Enquanto não houver escala, toda coleção entra com `nao_avaliada`.

### 11.7 O mapeamento de tipo — **equipe técnica propõe, curadoria confirma**

*Cada valor de `dc.type` corresponde a qual dos cinco tipos?* E, se `memoria` ou `normativo` não
aparecerem no acervo, confirmar que isso é o acervo e não um mapeamento que os esconde.

### 11.8 O contexto de cada coleção — **curadoria**

*De que situação saiu o material de cada coleção?* Uma a três frases por coleção. É o que resta do
campo `contexto`, e o que o marco pode usar para "dizer de onde fala".

### 11.9 Revisão amostral de OCR — **curadoria + comitê**

*Que fração se revisa, por coleção, e acima de que taxa de erro a coleção é reprocessada?*
`fase-1` §4.2 sugere 5% das páginas. A amostragem passa a ser por coleção porque o registro de
OCR por documento só existe para o que nós processarmos.

### 11.10 Reexportações — **curadoria + equipe técnica**

*Com que frequência o acervo é reexportado, e quem avisa?*

Cada exportação nova é um arquivo novo em `metadados/exportacao/`. A derivação compara com a
anterior — itens novos, removidos, alterados, handles trocados — e só então se decide o que
reindexar.

---

## 12. Como mudar o esquema depois

| Tipo de mudança | Custo | Exemplo |
|---|---|---|
| Acrescentar campo opcional derivado de coluna existente | Nenhum — rederivação | `serie` |
| Acrescentar campo que exigiria preenchimento por documento | **Impossível sob o acordo atual** | `contexto` por documento |
| Acrescentar linha à política de coleção | Baixo — decisão humana, uma por coleção | coleção nova na reexportação |
| Mudar a `restricao_uso` de uma coleção | Minutos — reescrita de payload dos pontos dela | coleção passa de `interno` a `publicavel` |
| Mudar uma linha de `mapa_tipo.csv` | **Reindexação** dos documentos daquele valor | "Relatório técnico" deixa de ser `academico` |
| Mudar a semântica de um valor | **Alto e perigoso** — o já derivado fica ambíguo | `interno` passar a incluir parceiros externos |
| O repositório trocar os handles | **Reindexação de tudo** — fora do controle do projeto | migração de DSpace |

**Procedimento:**

1. Toda mudança de esquema sobe a versão (cabeçalho) e entra no registro de alterações.
2. Toda mudança de mapa ou regra de derivação sobe `versao_da_derivacao`.
3. Mudança que afete comportamento do sistema — `restricao_uso`, `confiabilidade` — passa pelo
   comitê e dispara o harness de avaliação (`fase-0` §3.5).
4. Mudança que invalida o índice espera a próxima reindexação obrigatória e entra junto das
   outras ([roadmap](../roadmap.md) §5).

---

## 13. Checklist de aceite

Estende o portão G1 → 3 de [fase-1-corpus.md](../plano/fase-1-corpus.md) §7 com o que esta versão torna verificável — e
registra os critérios de lá que ela **não** atende.

- [ ] O esquema está na **versão 1**, aprovado pela direção, pelo comitê e pela curadoria.
- [ ] As pendências de §11 têm resposta escrita — em especial §11.3 e §11.4, que são decisões de
      aceitar menos do que a Fase 1 pede.
- [ ] Toda coleção presente na exportação tem linha na política, ou está fora do índice.
- [ ] Todo valor de `dc.type` presente na exportação tem linha em `mapa_tipo.csv`.
- [ ] Todo documento indexado tem os dezessete campos obrigatórios derivados.
- [ ] Nenhum documento de coleção com `direitos_situacao` em `nao_verificado` ou `negado` está no
      índice.
- [ ] Nenhum documento de coleção `fora_do_escopo`, nem com `triagem_automatica: bloqueado`, está
      no índice.
- [ ] Nenhum documento com `restricao_uso: vedado` está no índice — **testado com um documento
      posto em `bloqueios.csv`**, como pede o critério de aceite do portão G2 → 3.
- [ ] O filtro de restrição de uso é por **lista de permitidos** e roda dentro da query.
- [ ] Cada chunk tem `id`, `uri`, `pagina` e offset recuperáveis.
- [ ] `versao_embedding` está preenchida em todo ponto.
- [ ] A camada canônica existe separada do índice, e `hash_do_texto` bate com o arquivo.
- [ ] A derivação roda antes da indexação e **bloqueia** — não avisa.
- [ ] Um trecho citado na resposta leva, por link, à página pública do item no repositório.

**Critérios de `fase-1` §7 que esta versão não atende**, e o que os substitui:

| Critério | Substituto |
|---|---|
| "Todo documento no índice tem os seis metadados obrigatórios" | Quatro por documento (autoria, ano, tipo, restrição); contexto e confiabilidade por coleção |
| "Todo documento teve direitos verificados e o resultado registrado" | Declaração por coleção (§5.4) |
| Anonimização antes de indexar (`fase-1` §4.5) | Escopo por coleção e triagem automática que bloqueia (§5.5) |
| "A revisão amostral de OCR foi feita e está dentro do limite acordado" | Revisão amostral por coleção (§11.9) |

---

## Registro de alterações

| Versão | Data | O que mudou |
|---|---|---|
| 0 | 2026-09-09 | Primeira redação. Proposta da equipe técnica, a emendar pelo comitê e pela curadoria |
| 0.2 | 2026-09-21 | O acervo é um repositório DSpace já catalogado, cujos metadados não serão alterados nem preenchidos. Camada 1 passa a ser derivada; decisões humanas passam a ser por coleção (§5); identificador passa a ser o handle; mapa Dublin Core inverte de exportação para importação (§9); contexto, confiabilidade, direitos e dados pessoais saem do documento e vão para a coleção; campos sem origem no acervo removidos (§10); pendências de §11 reescritas. Análise em [limites-dos-metadados-do-acervo.md](limites-dos-metadados-do-acervo.md) |
