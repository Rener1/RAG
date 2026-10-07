# Fase 1 — Constituição do corpus

> [Índice dos documentos](../README.md) · ← [Fase 0](fase-0-desenho-e-contratos.md) · [Fase 2](fase-2-prototipo.md) →

**Duração estimada:** 3–6 meses (escala com o volume do acervo)
**Custo:** R$ 3.000–10.000 (digitalização e curadoria)
**Natureza:** documental e arquivística. É a maior massa de trabalho do projeto e a que menos parece "IA".

---

## 1. Objetivo

Transformar o acervo do Centro de Referência Paulo Freire num **corpus digital organizado, com direitos verificados,
metadados padronizados e proveniência rastreável até a página**.

> **Esta fase tem valor autônomo.** Ao final existe um acervo digital pesquisável — patrimônio institucional
> independentemente de qualquer IA. É o que sustenta o projeto se o financiamento parar no meio, e é um dos três
> argumentos de captação.

---

## 2. Pré-requisitos

- Lista negativa de dados em formato operacional (Fase 0).
- Partição público/restrito definida (Fase 0).
- Esquema de metadados acordado — **esta é a trava cara do projeto**, porque é trabalho humano e refazê-la significa
  reprocessar o acervo inteiro à mão.

---

## 3. Composição do corpus

| Bloco | Conteúdo | Cuidado principal |
|---|---|---|
| **Tradição freiriana** | Obras de Freire e de autores da tradição, em domínio público ou com autorização de uso | Verificação de direitos, obra a obra |
| **Produção da instituição** | Relatórios, assessorias, diagnósticos territoriais, formações, memórias de reunião | Maior concentração de dados pessoais. Anonimização obrigatória |
| **Marcos legais e normativos** | LDB, BNCC, PNE, planos municipais, pareceres do CNE | Estrutura muito distinta das obras teóricas — pede chunking próprio |
| **Produção acadêmica pertinente** | Teses, artigos, dissertações | Licenciamento variável |

---

## 4. Pipeline de ingestão — oito etapas

### 4.1 Aquisição

Levantamento físico e digital do acervo. Boa parte é material escaneado.
Registrar, para cada item: onde está o original, em que estado, se já existe versão digital.

### 4.2 OCR

Reconhecimento de texto em PDFs de imagem.

> **Qualidade de OCR é teto de qualidade do sistema.** Erro aqui se propaga silenciosamente até a resposta final —
> não gera exceção, gera citação errada.

Requisitos:
- Revisão amostral por lote (definir taxa de amostragem com o comitê; sugestão inicial: 5% das páginas por
  documento, com reprocessamento obrigatório do documento se a taxa de erro exceder o limite acordado).
- Reprocessamento **por documento**, sem rebuild total do índice.
- Registrar a ferramenta e a versão de OCR usadas, por documento.

### 4.3 Extração e normalização

PDF / DOCX / imagem → texto estruturado, **preservando divisão em páginas e seções**. A preservação de página não é
detalhe de formatação: é o que torna a citação verificável possível.

### 4.4 Metadados obrigatórios por documento

| Campo | Valores | Uso |
|---|---|---|
| Autoria | texto | Citação e "explicitar autoria" |
| Ano | data | Ordenação e contextualização |
| Contexto | texto livre | De que situação o documento saiu |
| Tipo | obra / relatório / normativo / acadêmico / memória | Estratégia de chunking |
| Nível de confiabilidade | escala definida pelo comitê | Ponderação na recuperação |
| **Restrição de uso** | interno / publicável / vedado | **Filtro aplicado na recuperação** |

> O campo de restrição é aplicado como **filtro dentro da query**, não como aviso na resposta. Um documento vedado
> nunca é recuperado; não é recuperado e depois escondido.

### 4.5 Filtro de dados pessoais

A lista negativa da Fase 0 vira **regra de ingestão**. Anonimização **antes** de indexar.

> Não existe "indexa e filtra depois": uma vez no índice, vaza.

Procedimento:
1. Triagem por tipo de documento (relatórios e memórias são os de maior risco).
2. Anonimização — substituição por identificadores consistentes quando o vínculo importa para a compreensão.
3. Registro do que foi anonimizado, para auditoria.
4. Documentos que não podem ser suficientemente anonimizados são marcados como **vedado** e não indexados.

### 4.6 Chunking sensível à estrutura

Quebrar por **seção/argumento**, não por contagem cega de caracteres.

| Tipo | Estratégia |
|---|---|
| Obra teórica | Por seção argumentativa; um trecho cortado no meio de um raciocínio de Freire perde o sentido que o torna citável |
| Relatório de assessoria | Por seção do relatório (diagnóstico, encaminhamentos, memória) |
| Marco normativo | Por artigo/inciso — a unidade de citação já existe no documento |
| Memória de reunião | Por pauta/deliberação |

### 4.7 Proveniência por chunk

Cada chunk carrega: **documento de origem, página, offset**.

> Sem isso a citação verificável é impossível — e citação é requisito, não enfeite. É a decisão de ingestão que
> mais dói se for esquecida, porque exige reprocessar tudo.

### 4.8 Indexação incremental e versionada

- Versão do modelo de embedding gravada junto de cada chunk.
- Pipeline de reindexação incremental, para trocar o embedding sem downtime.
- **Camada canônica preservada:** o texto extraído e normalizado é guardado separado do índice. Com ela, trocar
  embedding é um lote reprocessando sozinho — compute, não trabalho humano.

---

## 5. Separação de backups

| Ativo | Natureza | Política |
|---|---|---|
| **Corpus** (originais + camada canônica + metadados) | Insubstituível | Backup redundante, testado, com cópia fora da sede |
| **Índice** (vetorial + léxico) | Reconstruível | Backup por conveniência; pode ser regerado do corpus |

Confundir os dois leva a gastar proteção no que é barato e a subproteger o que é insubstituível.

---

## 6. Entregáveis

1. **Acervo digital organizado e pesquisável** — o entregável de valor autônomo.
2. **Planilha/base de catalogação** com todos os metadados preenchidos.
3. **Registro de verificação de direitos**, documento a documento: o que pode ser usado internamente, o que pode ser
   publicado, o que não pode ser usado.
4. **Registro de anonimização** para auditoria.
5. **Documentação do pipeline de ingestão**, escrita à medida que se constrói.
6. **Partição público/restrito aplicada** — conjunto público identificado e pronto para a Fase 2.

---

## 7. Critérios de aceite (portão G1 → 3)

- [ ] Todo documento no índice tem os seis metadados obrigatórios preenchidos.
- [ ] Todo documento teve direitos verificados e o resultado registrado.
- [ ] Nenhum documento marcado como vedado está no índice.
- [ ] Cada chunk tem documento, página e offset recuperáveis.
- [ ] A camada canônica existe separada do índice.
- [ ] A revisão amostral de OCR foi feita e está dentro do limite acordado.
- [ ] Existe um conjunto público identificado, autorizado a subir para GPU alugada.
- [ ] O pipeline está documentado a ponto de outra pessoa conseguir rodá-lo.

---

## 8. Riscos desta fase

| Risco | Prob. | Mitigação |
|---|---|---|
| OCR ruim contaminando o índice | Média | Revisão amostral; reprocessamento por documento sem rebuild total |
| Vazamento de dado pessoal pelo índice | Média | Lista negativa aplicada na ingestão; restrição filtrada dentro da query |
| Esquema de metadados mudar no meio | Média | Fechar o esquema **antes** de começar. É a trava cara: mudar depois é retrabalho humano em todo o acervo |
| Esquecer proveniência por chunk | Baixa, mas cara | Tratar como requisito de aceite do pipeline, não como melhoria |
| Curadoria virar projeto infinito | Média | Trabalhar por lotes priorizados: começar pelo material mais usado em assessoria, não pelo mais antigo |

---

## 9. Ordem de priorização sugerida

O corpus não precisa estar completo para a Fase 2 começar. Priorizar:

1. **Conjunto público, material mais citado em assessoria** — destrava a Fase 2 imediatamente.
2. Obras da tradição freiriana com direitos claros.
3. Marcos normativos (estrutura regular, OCR fácil, alto valor de consulta).
4. Produção institucional publicável.
5. Produção institucional restrita (mais trabalho de anonimização, só usável no servidor próprio).
