# Fase 3 — Avaliação e servidor próprio

**Duração estimada:** 2–4 meses (prazo de aquisição de hardware é risco de calendário)
**Custo:** R$ 11.500–31.000 (hardware completo)
**Natureza:** duas frentes independentes — a intelectualmente mais densa (avaliação) e a mais operacional (servidor).

---

## 1. Objetivo

Duas coisas que podem correr em paralelo:

1. Construir o **protocolo de avaliação** — o artefato intelectualmente mais denso do projeto, com valor de
   publicação acadêmica autônoma.
2. Migrar o sistema para **servidor próprio**, alcançando sigilo integral e custo marginal zero por uso.

---

## 2. Pré-requisitos

- Corpus catalogado (portão G1).
- Sistema em protótipo com modelo escolhido e marco pedagógico em primeira redação (portão G2).
- Relatório crítico de uso do piloto — é o insumo bruto dos casos-teste.

---

## Parte A — Avaliação (Camada 4)

### 3. Por que esta camada existe

Sem ela não há como saber se o sistema melhorou ou piorou a cada mudança. Tudo vira impressão subjetiva.

> **O modo de falha que ela existe para detectar não é erro factual — é a produção de "freirês":** vocabulário
> militante e bem articulado — conscientização, práxis, tema gerador, leitura de mundo — aplicado de forma genérica,
> sem ancoragem no território concreto e sem consequência prática. O texto soa impecável e não serve para nada.
>
> Esse modo de falha é **invisível para métricas automáticas de qualidade textual**. Só rubrica humana pega.

A camada de avaliação é a diferença entre um instrumento de trabalho e um gerador de retórica.

### 4. Os casos-teste

**80 a 150 situações reais de assessoria**, com critérios explícitos do que caracteriza resposta adequada.

**Elaborado pelo comitê pedagógico**, não pela equipe técnica. Isso não é formalidade: quem define o que conta como
resposta freiriana legítima é quem tem a prática.

Estrutura sugerida por caso:

| Campo | Conteúdo |
|---|---|
| Situação | O contexto real de assessoria de onde o caso veio |
| Demanda | A pergunta como um assessor a formularia |
| Tipo de demanda | Pedido de produto acabado / dúvida factual / exploração |
| Trechos que deveriam ser recuperados | Base do `recall@k` — permite avaliação automática da recuperação |
| Critérios de adequação | O que caracteriza uma resposta adequada **neste caso** |
| Modos de falha esperados | O que seria "freirês" aqui especificamente |

**Fontes dos casos:** registro de acertos e erros do piloto da Fase 2, mais situações de assessoria históricas
escolhidas pelo comitê para cobrir a variedade de demandas reais.

### 5. Rubrica

Critérios explícitos, aplicados por avaliadores humanos. Precisa distinguir, no mínimo:

- **Ancoragem** — a resposta se apoia em trecho identificável do acervo, ou improvisa?
- **Territorialidade** — a resposta trata do território concreto da demanda, ou é genérica?
- **Postura dialógica** — problematiza antes de responder, ou entrega produto?
- **Explicitação da disputa** — mostra posições divergentes, ou simula neutralidade?
- **Consequência prática** — o que sai serve como material de trabalho para um coletivo?

A rubrica é do comitê. Os critérios acima são um ponto de partida a ser reescrito por ele.

### 6. Harness automatizado

Roda o conjunto de casos **a cada mudança** de: modelo, embedding, chunking ou marco pedagógico.

Requisitos:
- **Temperatura fixa** e **snapshot de índice**, para que a comparação seja legítima.
- Execução acionada automaticamente por alteração do marco pedagógico.
- Histórico de execuções comparável ao longo do tempo.

### 7. Métricas separadas por camada

> **Não misturar: recuperação ruim e geração ruim têm correções opostas.**

| Camada | Métrica | Custo | Frequência |
|---|---|---|---|
| Recuperação | `recall@k` contra os trechos esperados | Automática, barata | A cada mudança |
| Geração | Aderência por rubrica humana | Cara | Por rodada de avaliação |

### 8. LLM como juiz

**Apenas como pré-filtro**, para priorizar o que vai à revisão humana. **Nunca como veredito.**

Motivo: um modelo julgando aderência freiriana tende a premiar exatamente o "freirês" — o texto bem articulado e
vazio é justamente o que um modelo reconhece como bom.

### 9. Registro de uso

Desde o primeiro piloto: acertos, erros e perguntas mal respondidas viram a **lista de trabalho da próxima iteração
do corpus**. O ciclo é: usar → registrar → corrigir corpus/marco → medir.

---

## Parte B — Servidor próprio (Rota B)

### 10. Especificação

| Item | Especificação | Faixa |
|---|---|---|
| Placa de vídeo | 16–24 GB VRAM | R$ 4.000–16.000 |
| Restante da máquina | CPU, 64 GB RAM, SSD, fonte robusta | R$ 6.000–12.000 |
| Nobreak e rede | **Não opcional** — protege o investimento | R$ 1.500–3.000 |
| Software | Ollama, Open WebUI, banco vetorial, modelos | R$ 0 |

**Capacidade:** roda com folga modelos de 8–14 B; com quantização, até ~30 B. Qualidade mais que suficiente para
redação, análise documental e diálogo sobre o acervo.

**Sobre preço:** valores são ordens de grandeza de agosto de 2026 e devem ser confirmados no momento da compra — o
mercado brasileiro de placas de vídeo oscila fortemente. Placa usada reduz muito o custo.

### 11. Migração

1. Instalar e validar o servidor na sede.
2. Migrar corpus completo — incluindo o **conjunto restrito**, que até aqui nunca subiu para lugar nenhum.
3. Reindexar no ambiente próprio.
4. Rodar o harness no servidor novo e comparar com a linha de base da GPU alugada.
5. **Desligar a GPU alugada.** Encerrar contrato, apagar dados no provedor, registrar o encerramento.

Só a partir deste ponto o sistema tem sigilo integral e pode tocar material com dado pessoal.

### 12. Operação desde o dia 1

- **Documentação de instalação escrita à medida que se instala.**
- Ferramentas de amplo uso, em vez de soluções elegantes e obscuras.
- Backup do corpus e do índice tratados separadamente: o corpus é insubstituível, o índice é reconstruível.
- Definir quem cuida da máquina — a desvantagem declarada da Rota B é justamente a necessidade de alguém que cuide.

---

## 13. Refinamento do marco pedagógico

Rodadas de ajuste com base nos resultados da avaliação. Cada rodada:

1. Comitê analisa os resultados da rubrica.
2. Propõe alteração no marco.
3. Alteração dispara o harness.
4. Compara-se antes e depois. Se piorou, reverte-se — e agora isso é verificável, não sentido.

---

## 14. Entregáveis

1. **Conjunto de 80–150 casos-teste** com critérios explícitos.
2. **Rubrica de aderência freiriana** — publicável de forma autônoma.
3. **Harness de avaliação** funcionando e acionado por mudança.
4. **Servidor próprio em operação na sede**, com sigilo integral.
5. **GPU alugada desligada**, com registro de encerramento.
6. **Marco pedagógico refinado**, com histórico de versões e resultados medidos.
7. **Documentação de operação e backup.**

---

## 15. Critérios de aceite

**Portão G3 → 5 (sustentação):**
- [ ] O harness roda o conjunto completo e produz resultado comparável entre execuções.
- [ ] `recall@k` e aderência humana são medidos e reportados separadamente.
- [ ] O sistema opera na sede, com o corpus restrito indexado.
- [ ] A GPU alugada está desligada e o contrato encerrado.
- [ ] Backup do corpus está testado — restauração verificada, não só configurada.
- [ ] Existe pelo menos uma rodada completa de refinamento do marco com efeito medido.

**Portão G3 → 4 (especialização), adicionalmente:**
- [ ] A avaliação identificou limites concretos, nomeados.
- [ ] Está documentado que esses limites **não** se resolvem por ajuste de marco pedagógico, chunking ou recuperação
      — com as tentativas registradas.

---

## 16. Riscos desta fase

| Risco | Prob. | Mitigação |
|---|---|---|
| Casos-teste virarem trabalho da equipe técnica | Alta | O comitê elabora. Se ele não tiver tempo, o cronograma se estende — não se terceiriza |
| Rubrica genérica demais para discriminar "freirês" | Alta | Testar a rubrica contra respostas deliberadamente vazias antes de usar em produção |
| LLM-juiz virar veredito por conveniência | Média | Regra escrita: pré-filtro apenas |
| Prazo de compra de hardware atrasar a fase | Média | Iniciar cotação no começo da Fase 3; a Parte A não depende do hardware |
| Perda do corpus na migração | Baixa, mas fatal | Backup testado antes de migrar |
| Índice reconstruído dar resultado diferente do protótipo | Média | Snapshot e comparação de harness antes/depois da migração |
