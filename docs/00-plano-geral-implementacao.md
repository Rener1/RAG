# IA Freiriana — Plano Geral de Implementação

> **Documentos de origem**
> - *IPF — Projeto desenvolvimento IA Freiriana* (Instituto Paulo Freire, 13/08/2026) — decisões pedagógicas, de governança e de captação.
> - *IA Freiriana — Plano Técnico* — recorte de engenharia (arquitetura, stack, pipelines).
>
> Este documento é o **plano de implementação**: junta os dois recortes numa sequência executável, com portões de
> entrada e saída por fase, responsáveis, entregáveis e critérios de aceite. Ele não reabre decisões dos documentos
> de origem — organiza a execução delas.

---

## 1. Visão em uma página

Construir um assistente conversacional de uso exclusivo do Instituto Paulo Freire, rodando em infraestrutura
própria, que consulta o acervo curado da instituição (Centro de Referência Paulo Freire) e responde **ancorado em
fonte verificável**, num desenho **dialógico** — problematizando antes de responder e entregando material de
trabalho para coletivos, não documentos acabados.

**O que estamos construindo (nível 4):** RAG + marco pedagógico sobre um modelo de pesos abertos.
**O que não estamos construindo:** modelo do zero (nível 1) nem treinamento continuado (nível 2). Ajuste fino
(nível 3) é condicional e fica para a Fase 4.

**O ativo do projeto não é o modelo.** É o corpus curado e o protocolo de avaliação. Modelos envelhecem em meses;
os dois outros duram décadas.

---

## 2. Os cinco princípios que atravessam todas as fases

Qualquer decisão em qualquer fase é testada contra estes cinco. Se conflitar, o princípio ganha.

1. **O comitê pedagógico é o dono do projeto.** A equipe técnica é serviço. O comitê tem poder de veto sobre
   mudanças de comportamento do sistema.
2. **O modelo é peça substituível, não alicerce.** Trocar de modelo tem de ser mudança de configuração.
3. **O investimento é no corpus e na avaliação.** Escolha que force retrabalho no corpus é cara; escolha que force
   troca de modelo é barata.
4. **Citação verificável é requisito, não enfeite.** Sem proveniência por trecho, o sistema vira oráculo.
5. **Cada fase entrega valor autônomo.** Se o financiamento parar no meio, o que foi feito continua valendo.

---

## 3. Mapa das fases

| Fase | Nome | Pergunta que responde | Entregável âncora | Arquivo |
|---|---|---|---|---|
| 0 | Desenho e contratos | Quem decide o quê, e sob que regras? | Termo de parceria + escopo + lista negativa como especificação | `fase-0-desenho-e-contratos.md` |
| 1 | Constituição do corpus | O que o sistema pode consultar, e com que garantias? | Acervo digital organizado e pesquisável | `fase-1-corpus.md` |
| 2 | Protótipo funcional | Isso funciona? Com qual modelo? | Sistema usável internamente + relatório crítico de uso | `fase-2-prototipo.md` |
| 3 | Avaliação e servidor próprio | Como sabemos se melhorou ou piorou? | Sistema na sede com sigilo integral + protocolo de avaliação | `fase-3-avaliacao-e-servidor.md` |
| 4 | Especialização (condicional) | O marco pedagógico esgotou seus limites? | Modelo especializado + artigo | `fase-4-especializacao.md` |
| 5 | Abertura e sustentação | Como isso sobrevive e se replica? | Metodologia publicada + rotina de manutenção | `fase-5-abertura-e-sustentacao.md` |

### Dependências e paralelismo

```
Fase 0 ──┬──> Fase 1 (corpus) ─────────┬──> Fase 3 ──> [Fase 4?] ──> Fase 5
         │                             │
         └──> Fase 2 (benchmark) ──────┘
```

- **Fases 1 e 2 correm em paralelo.** A curadoria é trabalho documental; o benchmark de modelos é técnico. Nenhum
  bloqueia o outro, desde que exista uma parcela pública do corpus pronta para testar.
- **A Fase 2 só pode começar** depois que a fronteira "corpus público vs. restrito" estiver resolvida (Fase 0),
  porque é ela que define o que pode subir para a GPU alugada.
- **A Fase 3 exige as duas anteriores fechadas**: o harness precisa de corpus e de sistema rodando.
- **A Fase 4 é condicional** e provavelmente desnecessária. Só entra se a avaliação da Fase 3 mostrar limite que
  ajuste de marco pedagógico, chunking e recuperação não resolvem.

---

## 4. Portões (o que autoriza avançar)

Cada portão é uma reunião curta do comitê pedagógico com a equipe técnica, com decisão registrada.

| Portão | Só passa se | Se não passar |
|---|---|---|
| **G0 → 1** | Parceria formalizada, comitê constituído, 5 decisões da §8 do projeto resolvidas, lista negativa escrita | Não iniciar digitalização. Corpus construído sem regra de uso precisa ser refeito |
| **G1 → 3** | Acervo catalogado com metadados completos, direitos verificados documento a documento, anonimização aplicada | Fase 3 sem corpus mede o vazio |
| **G2 → 3** | Modelo escolhido entre 3–4 testados, RAG rodando sobre parcela do corpus, marco pedagógico em primeira redação, relatório crítico de uso escrito | Repetir ciclo de protótipo antes de comprar hardware |
| **G3 → 4** | Casos-teste construídos e rodados; limites identificados **e** documentados como não resolvíveis por prompt/chunking/recuperação | Não fazer LoRA. Voltar a ajustar as camadas baratas |
| **G3 → 5** | Sistema em operação estável na sede, protocolo de avaliação publicável | Sustentar operação antes de abrir |

---

## 5. Papéis

| Papel | Quem | Responsabilidade |
|---|---|---|
| **Comitê pedagógico** (3–5 educadores do IPF) | A definir na Fase 0 | Dono do projeto. Escreve o marco pedagógico e os casos-teste. Veto sobre comportamento do sistema |
| **Coordenação institucional** | Direção do IPF | Parceria universitária, orçamento, decisões políticas da §8 |
| **Curadoria do acervo** | Centro de Referência + bolsista | Levantamento, verificação de direitos, metadados, anonimização |
| **Equipe técnica** | Bolsista de pós-graduação + apoio | Pipeline, RAG, orquestração, harness, servidor |
| **Parceria universitária** | Grupo de pesquisa | Orientação metodológica, bolsas, acesso a editais (inclusive Santos Dumont) |

**Regra de composição:** nenhuma função crítica pode depender de uma única pessoa sem documentação escrita. O risco
"projeto vira dependente de uma única pessoa técnica" está classificado como **alto** e é o mais barato de mitigar.

---

## 6. Orçamento consolidado (teto de R$ 30 mil)

| Rubrica | Fase | Faixa | Observação |
|---|---|---|---|
| GPU alugada (prototipagem) | 2 | R$ 800–3.000/mês | Desligada ao fim da Fase 3 |
| Placa de vídeo 16–24 GB | 3 | R$ 4.000–16.000 | Usada reduz muito; confirmar preço no momento da compra |
| Restante da máquina | 3 | R$ 6.000–12.000 | CPU, 64 GB RAM, SSD, fonte robusta |
| Nobreak e rede | 3 | R$ 1.500–3.000 | Não opcional |
| Digitalização e curadoria | 1 | R$ 3.000–10.000 | Bolsa de estagiário ou serviço pontual |
| Software | todas | **R$ 0** | Ollama, Open WebUI, bancos vetoriais e modelos são livres |
| Apoio técnico | 0–5 | via parceria | Bolsa de mestrando/doutorando |

O orçamento é essencialmente **hardware e pessoas**. Valores são ordens de grandeza de agosto de 2026; o mercado
brasileiro de placas de vídeo oscila fortemente.

---

## 7. Cronograma indicativo

Estimativas de esforço, **não compromissos**. A variável dominante é a disponibilidade do comitê pedagógico, não a
técnica.

| Fase | Duração estimada | Observação |
|---|---|---|
| 0 | 3–6 semanas | Curta, mas destrava tudo. Depende de agenda institucional |
| 1 | 3–6 meses | Maior massa de trabalho. Escala com o volume do acervo |
| 2 | 6–10 semanas | Em paralelo com a 1 |
| 3 | 2–4 meses | Inclui compra e instalação de hardware (prazo de aquisição é risco de calendário) |
| 4 | condicional | Depende de edital externo |
| 5 | contínuo | Vira rotina, não projeto |

---

## 8. Riscos consolidados

| Risco | Prob. | Onde é tratado |
|---|---|---|
| Produção de "freirês" — retórica sem ancoragem prática | Alta | Fase 3 (harness com rubrica humana); Fase 2 (formatos de saída) |
| Dependência de uma única pessoa técnica | Alta | Todas as fases (documentação desde o dia 1) |
| Modelo escolhido fica obsoleto | Alta | Fase 0 (contrato de interface); Fase 5 (rotina de troca) |
| Open WebUI virar produção por inércia | Média | Fase 2 (declarado protótipo descartável) |
| OCR ruim contaminando o índice | Média | Fase 1 (revisão amostral) |
| Vazamento de dado pessoal pelo índice | Média | Fase 0 (lista negativa) + Fase 1 (regra de ingestão) |
| Sistema substituir a escuta territorial em vez de prepará-la | Média | Fase 2 (marco pedagógico) + formação de uso |
| Financiamento não se sustenta após o piloto | Média | Faseamento com valor autônomo por etapa |

---

## 9. Como usar este conjunto de arquivos

```
00-plano-geral-implementacao.md      ← este documento: sequência, portões, papéis, orçamento
fase-0-desenho-e-contratos.md        ← decisões políticas e contratos entre camadas
fase-1-corpus.md                     ← pipeline de ingestão, metadados, direitos, anonimização
fase-2-prototipo.md                  ← benchmark de modelos, RAG, primeira redação do marco
fase-3-avaliacao-e-servidor.md       ← casos-teste, harness, hardware, migração
fase-4-especializacao.md             ← LoRA condicional, Santos Dumont
fase-5-abertura-e-sustentacao.md     ← publicação, replicação, manutenção
```

Cada arquivo de fase segue a mesma estrutura: objetivo, pré-requisitos, frentes de trabalho, entregáveis, critérios
de aceite, riscos da fase, decisões que a fase fecha e checklist final.

---

## 10. Próximo passo imediato

Fase 0. É curta, é barata e destrava tudo. Duas coisas em paralelo:

1. **Institucional:** constituir o comitê pedagógico e formalizar a parceria universitária.
2. **Documental:** começar o levantamento do acervo (Fase 1), que não depende de nenhuma decisão técnica pendente e
   é o único item do plano cujo valor independe do resto do projeto dar certo.
