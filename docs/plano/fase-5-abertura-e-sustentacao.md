# Fase 5 — Abertura e sustentação

> [Índice dos documentos](../README.md) · ← [Fase 4](fase-4-especializacao.md)

**Duração:** contínua. Vira rotina, não projeto.
**Custo:** operação corrente (custo marginal de uso é zero na Rota B)
**Natureza:** institucional e de manutenção.

---

## 1. Objetivo

Transformar o sistema em infraestrutura permanente da instituição e transformar o método em bem público replicável.

---

## 2. Pré-requisitos

- Sistema em operação estável na sede (portão G3 → 5).
- Protocolo de avaliação com histórico.
- **Decisão 1 da Fase 0 resolvida:** aberto ou exclusivo — é ela que define o que esta fase publica.

---

## 3. O que se publica

A via intermediária recomendada no documento original: **abrir o método e o marco pedagógico, manter reservado o
corpus institucional.**

| Artefato | Publicar? | Justificativa |
|---|---|---|
| **Marco pedagógico** | Sim | É a contribuição conceitual. Não expõe nada do acervo |
| **Protocolo de avaliação** (rubrica + método de construção dos casos) | Sim | Contribuição metodológica original, de interesse internacional |
| **Casos-teste** (conteúdo) | Avaliar caso a caso | Derivam de situações reais de assessoria; podem exigir anonimização |
| **Metodologia e documentação técnica** | Sim | Pipeline, decisões de arquitetura, aprendizados |
| **Corpus institucional** | Não | Reservado. É o ativo estratégico e contém material restrito |
| **Modelo especializado** (se Fase 4 ocorreu) | Decisão do comitê | Carrega, nos pesos, traços do corpus |

Licença aberta a definir com o comitê e a assessoria jurídica.

---

## 4. Formação de outras organizações

Replicação para outras organizações do campo. Componentes:

- Material de formação sobre o método — não sobre a ferramenta.
- Documentação de instalação já produzida desde a Fase 2, agora publicável.
- Acompanhamento das primeiras replicações, que retroalimentam o método.

**O que se replica é o desenho, não o sistema:** outra organização tem outro corpus, outro comitê e outro marco
pedagógico. Entregar o software sem o método reproduziria exatamente "ChatGPT com um prompt bonito".

---

## 5. Rotinas de sustentação

### 5.1 Atualização do corpus

| Rotina | Cadência sugerida | Responsável |
|---|---|---|
| Ingestão de nova produção institucional | Contínua, por lote | Centro de Referência |
| Revisão de metadados e restrições de uso | Anual | Curadoria + comitê |
| Reindexação após lote significativo | Por lote | Equipe técnica |
| Auditoria de anonimização | Anual | Curadoria |

O registro de uso — perguntas mal respondidas, lacunas encontradas — é a fonte prioritária do que ingerir a seguir.

### 5.2 Troca do modelo-base

O cenário de modelos muda a cada poucos meses. A arquitetura foi desenhada para que isso seja barato.

Procedimento:
1. Rodar o harness com o modelo candidato, mesma temperatura, mesmo snapshot de índice.
2. Comparar com a linha de base.
3. Trocar se houver ganho; manter se não. A decisão é medida, não sentida.

Cadência sugerida: avaliação de candidatos a cada 6–12 meses, ou quando surgir opção claramente superior.

### 5.3 Revisão do marco pedagógico

Revisto periodicamente pelo comitê. É um **artefato pedagógico por direito próprio** — não apenas configuração.
Toda alteração dispara o harness.

### 5.4 Operação

- Backup do corpus testado (restauração verificada, não só configurada).
- Nobreak com bateria em condição de uso.
- Documentação de instalação atualizada a cada mudança de infraestrutura.
- Sucessão técnica: nenhuma função crítica dependendo de uma única pessoa sem documentação.

---

## 6. Substituição do Open WebUI

Se o protótipo da Fase 2 ainda estiver em uso, esta fase é o limite. **Open WebUI é protótipo descartável.**

A aplicação própria precisa sustentar o que ele não sustenta:
- Orquestração multi-turno com estado — problematizar antes de responder.
- Citação obrigatória com rastreio até a página, validada contra o contexto recuperado.
- Marco pedagógico editável sem deploy, por quem não programa, com histórico e diff legível.
- Harness acionado a cada mudança.
- Formatos de saída estruturados: roteiro de escuta, matriz de contradição, temas geradores candidatos, perguntas
  para plenária.

O último item ainda é decisão em aberto: quais formatos, e qual a estrutura de cada um. Definição pedagógica com
implementação técnica direta.

---

## 7. Captação continuada

Três enquadramentos, para financiadores distintos:

| Enquadramento | Público | Argumento |
|---|---|---|
| **Soberania de dados na educação pública** | Fundações, poder público, cooperação | Redes municipais estão adotando ferramentas de IA estrangeiras sem política de proteção de dados de estudantes. Um sistema soberano, auditável e local é contraponto concreto e bem público replicável |
| **Preservação e ativação de acervo** | Editais culturais, fomento à memória | O acervo digital tem valor cultural e acadêmico elevado, independentemente do componente de IA |
| **Pesquisa aplicada em IA e educação crítica** | Agências de fomento, parceria universitária | O protocolo de aderência freiriana é contribuição metodológica original, publicável e de interesse internacional |

---

## 8. Entregáveis

1. **Publicação do marco pedagógico** sob licença aberta.
2. **Publicação do protocolo de avaliação** e da metodologia.
3. **Material de formação** para replicação.
4. **Rotinas de sustentação documentadas** — corpus, modelo, marco, operação.
5. **Aplicação própria** substituindo o Open WebUI.
6. **Plano de sucessão técnica** escrito.

---

## 9. Critérios de saúde do sistema em regime

Não são portões, são indicadores a acompanhar:

- [ ] O harness rodou nos últimos 6 meses e o resultado está registrado.
- [ ] O corpus recebeu ingestão nos últimos 6 meses.
- [ ] O marco pedagógico foi revisto no último ano.
- [ ] A restauração de backup foi testada no último ano.
- [ ] Mais de uma pessoa consegue operar o servidor.
- [ ] O registro de uso está sendo alimentado por quem usa.

Se três ou mais indicadores falharem simultaneamente, o comitê deve reavaliar contra o **critério de desistência**
definido na Fase 0.

---

## 10. Risco de fundo desta fase

| Risco | Mitigação |
|---|---|
| Sistema substituir a escuta territorial em vez de prepará-la | Desenho dialógico; marco que recusa produzir documento final; **formação de uso para a equipe** — este último é o único que age sobre a prática, não sobre o software |
| Manutenção parar por falta de responsável designado | Rotina com responsável nomeado, não "a equipe técnica" |
| Sistema virar oráculo na prática de uso, apesar do desenho | Registro de uso + revisão periódica pelo comitê de como está sendo usado, não só de como responde |
