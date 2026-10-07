# Fase 0 — Desenho e contratos

> [Índice dos documentos](README.md) · ← [Plano geral](00-plano-geral-implementacao.md) · [Fase 1](fase-1-corpus.md) →

**Duração estimada:** 3–6 semanas
**Custo:** ~R$ 0 (tempo institucional)
**Natureza:** política e organizacional. Quase nenhuma linha de código.

---

## 1. Objetivo

Fixar quem decide o quê, sob que regras, e transformar as decisões institucionais em **especificações** que a
engenharia possa cumprir. É a fase mais barata do projeto e a única cujo erro contamina todas as outras: um corpus
construído antes de existir uma regra de uso precisa ser refeito documento a documento.

---

## 2. Pré-requisitos

- Decisão da direção do IPF de tocar o projeto.
- Interlocução aberta com pelo menos uma universidade candidata a parceira.

---

## 3. Frentes de trabalho

### 3.1 Parceria universitária

- Identificar grupo de pesquisa, preferencialmente vinculado a **programa de pós-graduação em Educação com linha em
  políticas educacionais**.
- Definir orientador responsável, bolsista e escopo.
- Verificar se o grupo tem ou pode obter acesso a editais de infraestrutura (relevante para a Fase 4 —
  supercomputador Santos Dumont, LNCC).
- **Formato preferido:** parceria institucional, não contrato com pessoa física. Isso mitiga diretamente o risco
  "projeto vira dependente de uma única pessoa técnica".

### 3.2 Constituição do comitê pedagógico

- 3 a 5 educadores da instituição.
- **Este comitê é o dono do projeto.** A equipe técnica é serviço.
- Definir explicitamente o poder do comitê: recomenda-se **poder de veto** sobre mudanças no comportamento do
  sistema, não função apenas consultiva.
- Definir cadência de reunião e como o veto é exercido na prática (ver decisão técnica em aberto nº 3 — onde vive
  o marco pedagógico).

### 3.3 As cinco decisões políticas

Nenhuma tem resposta óbvia. Todas precisam estar resolvidas e **escritas** antes da Fase 1.

| # | Decisão | Opções | Consequência prática |
|---|---|---|---|
| 1 | **Aberto ou exclusivo?** | Abrir tudo / manter tudo fechado / **via intermediária: abrir método e marco pedagógico, reservar o corpus institucional** | Define o que a Fase 5 publica |
| 2 | **Quem responde pelo que o sistema diz?** | Política interna de assinatura e revisão | Precisa estar escrito **antes do primeiro uso externo** |
| 3 | **Que dados jamais entram no sistema?** | Lista negativa explícita | Vira regra de ingestão na Fase 1 |
| 4 | **Composição e poder do comitê** | Consultivo / com veto | Determina o desenho técnico do marco pedagógico |
| 5 | **Critério de desistência** | Condições objetivas de encerramento | Sem isso, projetos de tecnologia consomem recursos por inércia |

**Sobre a decisão 3 — lista negativa.** O ponto de partida do documento original: dados identificáveis de
estudantes, informações de saúde, relatos de violência, deliberações sigilosas de conselhos. Essa lista precisa
sair da Fase 0 em forma operacional: não "evitar dados sensíveis", mas uma enumeração que um curador consiga
aplicar documento a documento sem interpretar.

**Sobre a decisão 5 — critério de desistência.** Sugestão de formulação: condições mensuráveis observadas ao fim de
uma fase (ex.: corpus abaixo de um volume mínimo utilizável; avaliação da Fase 3 abaixo de um patamar de aderência
definido pelo comitê; perda da parceria universitária sem substituição em X meses). O ponto não é acertar o número
agora, é ter o número escrito antes de haver custo afundado.

### 3.4 Fronteira corpus público vs. restrito

Decisão técnica de consequência imediata: **a Fase 2 usa GPU alugada**, onde os dados transitam por infraestrutura
de terceiros. Isso é aceitável para prototipagem com acervo público e **inadequado** para qualquer material com
dados pessoais.

Portanto, a Fase 0 precisa definir a partição:

- **Conjunto público** — obras em domínio público, produção já publicada, marcos normativos (LDB, BNCC, PNE,
  pareceres do CNE), produção acadêmica. Pode subir para a Rota A.
- **Conjunto restrito** — relatórios de assessoria, diagnósticos, memórias de reunião, qualquer material com dado
  pessoal. Só entra no servidor próprio (Rota B).

Se essa fronteira não estiver resolvida, a Fase 2 fica bloqueada.

### 3.5 Contratos entre as quatro camadas

Trabalho técnico da fase. O objetivo é que cada camada possa evoluir sem quebrar as outras.

| Contrato | O que precisa ficar fixo |
|---|---|
| **Corpus → Recuperação** | Formato do chunk: texto, documento de origem, página, offset, versão do embedding, restrição de uso |
| **Recuperação → Motor** | Interface própria de inferência: `gerar()` e `embutir()`, com o runtime falando contrato compatível com a API da OpenAI. Trocar de modelo = mudar configuração |
| **Marco pedagógico → Orquestrador** | O marco é dado versionado carregado em tempo de execução, nunca prompt hardcoded |
| **Tudo → Avaliação** | Toda mudança de modelo, embedding, chunking ou marco dispara o harness |

Não é preciso implementar nada disso na Fase 0. É preciso **escrever a interface** — o que cada camada promete às
outras — em duas ou três páginas.

---

## 4. Entregáveis

1. **Termo de parceria assinado** com a universidade.
2. **Documento de escopo** de duas páginas.
3. **Ata de constituição do comitê pedagógico**, com composição e poderes.
4. **Documento das cinco decisões**, com as respostas escritas e datadas.
5. **Lista negativa de dados** em formato operacional (checklist aplicável por curador).
6. **Partição público/restrito** do acervo, como regra de classificação.
7. **Documento de contratos entre camadas** (2–3 páginas).

---

## 5. Critérios de aceite (portão G0 → 1)

- [ ] Existe um documento assinado com a universidade parceira.
- [ ] O comitê pedagógico tem nomes, cadência de reunião e poderes escritos.
- [ ] As cinco decisões têm resposta escrita — não "em discussão".
- [ ] A lista negativa é aplicável por alguém que não participou da discussão.
- [ ] Está escrito o que pode e o que não pode subir para GPU alugada.
- [ ] Está escrito o contrato de interface da camada de inferência.

---

## 6. Riscos desta fase

| Risco | Mitigação |
|---|---|
| Fase 0 se arrastar por meses por agenda institucional | Fase 1 (levantamento do acervo) pode começar em paralelo — não depende das decisões técnicas |
| Decisões ficarem genéricas demais para serem aplicadas | Teste de operacionalidade: entregar a lista negativa a alguém de fora e ver se consegue classificar 10 documentos sem perguntar nada |
| Comitê pedagógico virar figurativo | Poder de veto escrito + cadência fixa + os casos-teste da Fase 3 são produzidos por ele, não pela equipe técnica |
| Parceria não se materializar | Não bloqueia Fases 1 e 2. Bloqueia a Fase 4 e enfraquece a captação |

---

## 7. O que esta fase deliberadamente **não** faz

- Não escolhe modelo de linguagem. A escolha é da Fase 2, por benchmark.
- Não escolhe banco vetorial. Decisão de operação, tomada na Fase 2.
- Não compra hardware. Compra é da Fase 3, depois de o protótipo mostrar o porte necessário.
- Não escreve o marco pedagógico. Primeira redação é da Fase 2, com o comitê já tendo visto o sistema funcionar.
