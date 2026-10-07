# Fase 2 — Protótipo funcional

> [Índice dos documentos](../README.md) · ← [Fase 1](fase-1-corpus.md) · [Fase 3](fase-3-avaliacao-e-servidor.md) → · [Roadmap](../roadmap.md)

**Duração estimada:** 6–10 semanas (em paralelo com a Fase 1)
**Custo:** R$ 800–3.000/mês de GPU alugada
**Natureza:** técnica e exploratória. É a fase de aprender, não de consolidar.

---

## 1. Objetivo

Colocar um sistema RAG funcionando sobre a parcela pública do corpus, escolher o modelo por comparação medida em vez
de por reputação, e produzir a **primeira redação do marco pedagógico** — escrita pelo comitê pedagógico já tendo
visto o sistema funcionar.

---

## 2. Pré-requisitos

- Fronteira público/restrito definida (Fase 0) — sem ela, nada pode subir para GPU alugada.
- Parcela do corpus público pronta (Fase 1, priorização item 1).
- Contrato de interface de inferência escrito (Fase 0).

---

## 3. Restrição operacional que define a fase

A Rota A (GPU alugada) faz os dados **transitarem por infraestrutura de terceiros**. Isso é:

- **aceitável** para prototipagem com acervo público;
- **inadequado** para qualquer material com dados pessoais.

Isso não é recomendação. É o critério que define o que pode ser carregado. Contratar com datacenter em território
brasileiro, sob acordo de confidencialidade e conformidade com a LGPD.

---

## 4. Frentes de trabalho

### 4.1 Instalação da base

- **Ollama** como runtime de inferência. Escolhido por troca trivial de modelo e ampla adoção — a ampla adoção é
  mitigação direta do risco de dependência de uma única pessoa técnica.
- **Open WebUI** como interface.
- Alternativas para depois, se surgir necessidade de throughput ou controle fino: `llama.cpp`, `vLLM`.

> **Documentar a instalação à medida que se instala.** Não depois. O risco "projeto depende de uma única pessoa
> técnica" é alto e é o mais fácil de mitigar com disciplina barata.

### 4.2 Ressalva sobre o Open WebUI

Open WebUI + Ollama entrega um RAG funcional em dias, e é a escolha certa **para esta fase**. Mas o RAG embutido é
genérico: chunking padrão, recuperação padrão, prompt de sistema como campo de texto. **Ele não sustenta os
requisitos de orquestração dialógica** — multi-turno com estado, citação obrigatória com rastreio até a página,
harness rodando a cada mudança.

> Tratar o Open WebUI como **protótipo descartável**, não como fundação. Se ele virar produção por inércia, o
> projeto perde exatamente o que o diferencia de "ChatGPT com um prompt bonito".

Marcar isso como decisão registrada, não como intenção.

### 4.3 Benchmark de modelos

Testar **3 a 4 modelos** com o **mesmo conjunto de perguntas**.

Famílias candidatas:

| Família | Licença | Nota |
|---|---|---|
| Qwen | Apache 2.0 | Forte suporte multilíngue |
| Mistral | aberta | — |
| Gemma | aberta | — |
| Llama | licença de comunidade Meta | Permissiva para o porte de uma OSC, mas **não** open source formal |
| Sabiá (Maritaca AI) | verificar | Modelo brasileiro, avaliar para PT-BR |
| Amazônia IA (WideLabs) | verificar | Plataforma brasileira |

**Porte alvo:** 8–14 B rodam com folga em 16–24 GB de VRAM; até ~30 B com quantização.

> **Não fixar o modelo como decisão permanente.** O cenário muda a cada poucos meses. O resultado do benchmark é
> "com o que começamos", não "o que usamos". A arquitetura tem de permitir a troca por configuração.

**Método do benchmark:** mesmo conjunto de perguntas, mesma temperatura, mesmo snapshot de índice. Registrar as
saídas para comparação posterior — esse conjunto vira embrião dos casos-teste da Fase 3.

### 4.4 Camada de recuperação (RAG)

**Busca híbrida, não puramente vetorial.** Combinar similaridade vetorial com busca léxica full-text em português
(remoção de acentos, tolerância a erro de digitação), fundindo os dois rankings.

O motivo é específico deste corpus: o vocabulário freiriano — *tema gerador*, *conscientização*, *práxis*, *leitura
de mundo*, *situação-limite* — é jargão denso, e é exatamente onde embeddings genéricos derrapam, aproximando
termos que na tradição têm sentidos distintos. **A busca léxica ancora o que o vetor dispersa.**

Requisitos:
- Filtro de restrição de uso aplicado **dentro** da query, antes do ranking. Nunca após recuperar.
- Recuperação avaliável isoladamente: `recall@k`, **sem gerar uma linha de texto**. Se a busca traz o trecho errado,
  nenhum modelo salva a resposta — e essa medição é barata e precede o resto.

### 4.5 Decisões técnicas a fechar nesta fase

| Decisão | Critério |
|---|---|
| **Modelo de embeddings** | Multilíngue com bom PT-BR. Acoplada ao chunking: pedaço maior que a janela de entrada é truncado **em silêncio**, e a cauda some da busca sem erro nenhum |
| **Banco vetorial** | pgvector, Qdrant ou Chroma. Critério é **operação** (quem mantém, como faz backup), não desempenho — no volume esperado, os três servem |
| **Estratégia de chunking** | Sensível à estrutura, por tipo de documento (ver Fase 1) |

Trocar o embedding depois custa uma reindexação: compute, não trabalho humano. Não é decisão travada.

### 4.6 Primeira redação do marco pedagógico

Escrita **pelo comitê pedagógico**, em linguagem natural, não por programadores. É a "constituição freiriana" do
sistema. Precisa responder:

- Como o sistema se comporta diante de um pedido de produto acabado?
- O que ele recusa fazer?
- Que perguntas ele devolve antes de responder?
- Em que formato ele entrega?

**As quatro diretrizes e suas consequências técnicas:**

| Diretriz | Consequência de código |
|---|---|
| **Problematizar antes de responder** | Fluxo padrão não é pergunta→resposta. É pergunta→devolução de perguntas→construção conjunta. Exige orquestração multi-turno com estado e um classificador do tipo de demanda (produto acabado / dúvida factual / exploração) |
| **Explicitar fonte e autoria** | Citação verificável em toda afirmação relevante → proveniência por chunk, saída estruturada com âncoras, validação de que o citado existe no contexto recuperado |
| **Assumir posição e mostrar a disputa** | Recuperação busca **posições divergentes**, não só os k trechos mais similares — que tendem a ser redundantes entre si. Exige diversificação no ranking |
| **Recusar o produto acabado** | Saída padrão é material de trabalho para um coletivo: roteiros de escuta, temas geradores candidatos, matrizes de contradição, perguntas para plenária. São **formatos de saída**, com estrutura e validação próprias |

**O marco como artefato de software** — três exigências que um prompt hardcoded não atende:
- **Versionado**, com histórico e diff legível (o comitê tem veto sobre mudanças de comportamento).
- **Editável sem deploy**, por quem não programa.
- **Toda alteração dispara o harness de avaliação** (Fase 3).

Nesta fase o harness ainda não existe; a exigência é preparar o marco para viver fora do código desde já.

### 4.7 Uso piloto restrito

Grupo pequeno de assessores, com **registro sistemático de acertos e erros**. Esse registro não é impressão solta:
vira a lista de trabalho da próxima iteração do corpus e o insumo bruto dos casos-teste da Fase 3.

Formato mínimo de registro por interação problemática: pergunta feita, o que o sistema respondeu, o que estava
errado, o trecho que deveria ter sido recuperado (se aplicável).

---

## 5. Entregáveis

1. **Sistema utilizável internamente** — RAG sobre a parcela pública do corpus.
2. **Relatório de benchmark** dos 3–4 modelos, com o conjunto de perguntas e as saídas registradas.
3. **Primeira redação do marco pedagógico**, assinada pelo comitê.
4. **Relatório crítico de uso** do piloto, com acertos e erros catalogados.
5. **Documentação de instalação** completa o suficiente para outra pessoa reproduzir.
6. **Decisões fechadas:** embedding, banco vetorial, estratégia de chunking, modelo inicial.

---

## 6. Critérios de aceite (portão G2 → 3)

- [ ] 3–4 modelos foram testados com o mesmo conjunto de perguntas e o resultado está escrito.
- [ ] O sistema cita fonte com documento e página verificáveis.
- [ ] O filtro de restrição de uso funciona dentro da query — testado com um documento marcado como vedado.
- [ ] `recall@k` é medível isoladamente, sem gerar texto.
- [ ] O marco pedagógico existe em primeira redação, escrito pelo comitê.
- [ ] O marco vive fora do código, versionado.
- [ ] Existe relatório crítico de uso do piloto.
- [ ] A instalação está documentada.
- [ ] Está registrado por escrito que o Open WebUI é descartável.

---

## 7. Riscos desta fase

| Risco | Prob. | Mitigação |
|---|---|---|
| Open WebUI virar produção por inércia | Média | Declarar descartável por escrito; não construir nada sobre ele que doa jogar fora |
| Escolher modelo cedo demais e amarrar a arquitetura | Média | Interface de inferência isolando o runtime; troca por configuração |
| Chunk maior que a janela do embedding truncar em silêncio | Média | Validar tamanho de chunk contra a janela do modelo escolhido; testar explicitamente a recuperação da cauda de chunks longos |
| Carregar material restrito na GPU alugada | Baixa, mas grave | Partição aplicada como regra automatizada no pipeline, não como cuidado manual |
| Piloto gerar impressões em vez de dados | Alta | Formato de registro fixo desde a primeira sessão |
