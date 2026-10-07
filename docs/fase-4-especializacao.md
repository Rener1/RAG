# Fase 4 — Especialização (condicional)

> [Índice dos documentos](README.md) · ← [Fase 3](fase-3-avaliacao-e-servidor.md) · [Fase 5](fase-5-abertura-e-sustentacao.md) →

**Duração estimada:** depende de edital externo
**Custo:** R$ 5.000–60.000 se feita comercialmente; possivelmente ~R$ 0 via edital
**Natureza:** condicional e **provavelmente desnecessária**. Está no plano por completude.

---

## 1. Advertência de abertura

> **Só executar se a avaliação da Fase 3 mostrar limites que o ajuste do marco pedagógico não resolve.**

Antes de considerar esta fase, esgotar:

1. Ajuste do **marco pedagógico**
2. Ajuste do **chunking**
3. Ajuste da **recuperação**

Os três são reversíveis, mensuráveis e ordens de grandeza mais baratos. O ajuste fino não é nenhuma das três coisas.

**E o erro clássico:** ajuste fino feito sobre um acervo mal curado apenas ensina o modelo a **soar** freiriano sem
ser freiriano — e, pior, torna o erro impossível de rastrear, porque passa a estar nos pesos em vez de estar num
trecho recuperável. É exatamente o modo de falha que o projeto inteiro foi desenhado para evitar.

---

## 2. Pré-requisitos (portão G3 → 4)

Todos obrigatórios. Se algum faltar, a resposta é voltar à Fase 3.

- [ ] Corpus consolidado e curado.
- [ ] Protocolo de avaliação funcionando, com histórico de execuções.
- [ ] Limites concretos identificados e **nomeados** — não "o sistema poderia ser melhor".
- [ ] Registro documentado das tentativas de resolver esses limites por marco pedagógico, chunking e recuperação, e
      da razão de terem falhado.
- [ ] Comitê pedagógico aprovou a entrada nesta fase.

---

## 3. O que é

**Ajuste fino leve (LoRA)** com exemplos de diálogo freiriano de **alta qualidade produzidos pela própria
instituição**. Nível 3 na escala de intervenção do documento original — alguns milhares de exemplos, não
retreinamento.

O que muda: o comportamento e o estilo do modelo.
O que **não** muda: a fonte das respostas continua sendo o RAG. O ajuste fino não substitui a recuperação, e a
exigência de citação verificável permanece intacta.

---

## 4. Construção do conjunto de treino

O gargalo desta fase não é compute. É produzir exemplos bons.

| Requisito | Detalhe |
|---|---|
| **Origem** | Diálogos produzidos pela instituição, não gerados por outro modelo |
| **Qualidade** | Cada exemplo precisa ser um caso que o comitê assinaria como resposta freiriana adequada |
| **Cobertura** | Cobrir os tipos de demanda mapeados nos casos-teste |
| **Separação** | Exemplos de treino **não** podem se sobrepor aos casos-teste da Fase 3, ou a avaliação vira teatro |
| **Restrição de dados** | A lista negativa se aplica integralmente. Exemplos com dado pessoal são anonimizados antes |

A separação entre treino e avaliação é a exigência mais fácil de violar por descuido e a que invalida todo o
resultado.

---

## 5. Infraestrutura de processamento

**Esta é a etapa que mais se beneficia da parceria universitária.**

O processamento pode ser solicitado ao **supercomputador Santos Dumont, do LNCC**, cujos editais são abertos
periodicamente por universidades parceiras e cuja infraestrutura foi ampliada em 2025 justamente para treinamento
de modelos de IA.

Providências:
- Acompanhar calendário de editais via o grupo de pesquisa parceiro.
- Verificar o Programa de Embaixadores do Santos Dumont como via de acesso.
- Preparar a submissão com antecedência: os pré-requisitos da §2 são também o corpo da justificativa do pedido.

**Alternativa:** GPU alugada por hora para a rodada de treino. Restrição: só com material que possa transitar por
terceiros — o que na prática limita muito, já que os melhores exemplos vêm da produção institucional.

---

## 6. Método

1. Congelar a linha de base: rodar o harness completo no sistema atual, guardar o resultado.
2. Construir e revisar o conjunto de exemplos.
3. Rodada de LoRA.
4. **Rodar o harness no modelo ajustado, com a mesma temperatura e o mesmo snapshot de índice.**
5. Comparar contra a linha de base, por camada — recuperação não deve mudar (não foi tocada); a variação tem de
   estar na geração.
6. Se não houve ganho mensurável de aderência, **descartar o modelo ajustado**. A arquitetura de modelo trocável
   torna isso barato.

O passo 6 precisa estar acordado antes do passo 1. Ajuste fino que não melhora a rubrica é custo afundado, e a
tentação de mantê-lo por ter dado trabalho é previsível.

---

## 7. Entregáveis

1. **Conjunto de exemplos de diálogo freiriano** curado pela instituição — ativo institucional independente do
   ajuste fino ter funcionado.
2. **Modelo especializado**, se e somente se houver ganho medido.
3. **Artigo acadêmico** sobre método e resultados — inclusive se o resultado for negativo, o que é publicável e
   útil.
4. **Relatório comparativo** de harness, antes e depois.

---

## 8. Riscos desta fase

| Risco | Prob. | Mitigação |
|---|---|---|
| Ajuste fino sobre corpus mal curado | Alta se os pré-requisitos forem afrouxados | Portão G3 → 4 tratado como obrigatório, não como formalidade |
| Contaminação treino/teste | Média | Separação verificada por terceiro antes do treino |
| Modelo ajustado ficar preso ao projeto por custo afundado | Média | Critério de descarte acordado antes de começar |
| Ajuste fino gerar "freirês" mais convincente | Média | Rubrica humana; LLM-juiz nunca como veredito |
| Erro deixar de ser rastreável | Alta por natureza | Manter RAG e citação obrigatória; o ajuste muda a forma, não a fonte |
| Edital não sair no prazo | Média | A fase é condicional e sem urgência. Não bloqueia a Fase 5 |

---

## 9. Se a resposta for "não fazer"

É o desfecho mais provável e **não é um fracasso**. Significa que o marco pedagógico, o corpus e a recuperação
resolveram o problema — que era a hipótese de trabalho do projeto desde o início.

Nesse caso: registrar a decisão e a evidência que a sustenta. Isso é, por si só, um resultado publicável — a
demonstração de que contextualização e desenho dialógico bastam, sem alterar pesos.
