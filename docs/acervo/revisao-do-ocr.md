# Revisão do OCR

> [Índice dos documentos](../README.md) · [Esquema de metadados](esquema-de-metadados.md) §4.5 e §11.9 · [Fase 1 — Corpus](../plano/fase-1-corpus.md) §4.2 · [Medições](../engenharia/medicoes.md#extração-do-acervo--o-limiar-ainda-não-foi-medido)

**Aberto em:** 2026-10-23 · **Mantido por:** equipe técnica, com o que a revisão for encontrando

## Para que serve este documento

É o registro dos problemas encontrados no texto que o OCR tirou dos PDFs do acervo, **venham eles
do OCR ou do próprio documento original** (datilografia, carimbo, anotação, digitalização). Não se
faz distinção, porque os dois chegam do mesmo jeito ao texto indexado e os dois limitam a
qualidade das respostas. Quando a origem importa para a correção, a descrição diz qual é. Serve para
levar à reunião **que tipos de problema existem, onde aparecem e o que dá para fazer com cada um**.
Com isso a curadoria e o comitê podem decidir duas coisas que o
[esquema](esquema-de-metadados.md) §11.9 deixa em aberto: quanto se revisa por coleção, e acima de
que taxa de erro uma coleção volta para o OCR.

A [fase 1](../plano/fase-1-corpus.md) §4.2 explica por que isso importa: **a qualidade do OCR é o
teto da qualidade do sistema.** Um erro de OCR não trava nada. Ele vira uma citação errada que
parece perfeita.

**Como ler e acrescentar:**

- Cada linha do [registro](#2-registro) é **um tipo de problema**, com um exemplo real. Uma
  ocorrência nova de um problema já registrado entra na coluna "onde ocorre", e não vira linha
  nova.
- **Cite no máximo algumas palavras do documento.** Este arquivo é versionado e vai para o
  GitHub junto com o código. O documento se identifica pelo handle, e o texto completo fica em
  `data/texto_acervo/`, que não é versionado.
- O texto extraído de cada PDF fica em `data/texto_acervo/<handle>/<arquivo>.txt`, com as páginas
  separadas por quebra de página. O `.json` ao lado diz quais páginas passaram por OCR.
- **Gravidade:**
  - **alta:** muda o sentido ou a citação, como uma palavra trocada por outra que existe, um
    número errado, um trecho perdido ou atribuído à página errada;
  - **média:** atrapalha a busca, mas quem lê entende;
  - **baixa:** só aparência.

---

## 1. O que já passou pelo OCR

Ferramenta: OCRmyPDF 16.13 com Tesseract 5.5.3, idioma `por` (português), com correção de
inclinação e de rotação. Comando: `python3 main.py extrair`. Situação em 2026-10-23:

| Medida | Valor |
|---|---|
| Itens (handles) | 38, todos da coleção 7891/3631 |
| PDFs | 39 (o item 7891/90137 tem dois) |
| Páginas | 296, das quais 238 passaram por OCR |
| PDFs com camada de texto própria | 1. Os outros 38 eram só imagem |
| Idioma pelo catálogo (`dc.language.iso`) | 19 `pt`, 9 inglês (`en`, `en_US`), 5 `es`, 4 `fr`, 1 `other`, 1 vazio, contados por PDF |
| Páginas que ficaram quase sem texto mesmo depois do OCR | 12: 7891/90109 pp. 2–12 e 7891/25 p. 1 |

---

## 2. Registro

Em ordem de gravidade. Revisado por Rener e pela equipe técnica, e conferido contra a imagem
ou o `.txt` de cada exemplo.

| Problema | Descrição | Exemplo real e onde ocorre | Gravidade | Pode ser corrigido? Como |
|---|---|---|---|---|
| **P1 · Página perdida** | Uma página que tem texto legível sai vazia no `.txt`. O Tesseract binariza a página (separa tinta de fundo) com um limiar único para a página inteira. Com fundo cinza e uma faixa escura na borda, o limiar falha e ele descarta a página como se não tivesse texto | 7891/90109, datilografado em inglês: **11 das 12 páginas vazias** (pp. 2–12). 7891/25 p. 1 também saiu quase vazia, ainda não conferida | **alta** | **Sim, provavelmente.** Com a binarização adaptativa (`--tesseract-thresholding sauvola`), que calcula o limiar por região, as páginas do 7891/90109 voltaram com 2.250–2.930 caracteres cada, mas o começo das linhas ainda vem com ruído. Falta medir antes de virar padrão e reprocessar o documento. O caso também se detecta sozinho: as páginas quase vazias já vêm listadas no `.json` de cada PDF |
| **P11 · Linhas embaralhadas** | Com a página levemente inclinada, o OCR perde a linha que está lendo: corta a linha no meio, continua na linha de baixo, volta para a de cima e desloca palavras para longe do lugar. A inclinação varia entre as quatro páginas do documento. A correção de inclinação (`--deskew`) estava ligada e endireita página por página, então a variação entre páginas, sozinha, não explica a falha. Na p. 4 a correção não bastou, por uma causa ainda a medir: o ângulo pode ter ficado acima do que ela corrige, ou a inclinação pode mudar dentro da própria página. O texto continua todo lá, mas fora de ordem, então a frase citada não é a do documento | O parágrafo `O Clube que nasceu do debate…` sai com `Começa a aj` / `udar` e `preocupar-` / `se com` em linhas trocadas, e a palavra `merenda,` do fim da primeira linha vai parar sozinha antes do parágrafo. 7891/1133 p. 4 (linhas 171–186 do `.txt`) | **alta** | **Talvez.** Testar a limpeza e o endireitamento da página antes do OCR (`--clean`, com o `unpaper`), rasterizar em resolução maior (`--oversample 300`) e outro modo de segmentação do Tesseract. Precisa de medição nesta página. Se nada resolver, revisão humana no eScriptorium (§6), que segmenta pela linha de base de cada linha, mesmo inclinada, e deixa corrigir a ordem das linhas. Para achar os casos: linha que termina no meio de uma palavra sem hífen e não continua na linha seguinte |
| **P2 · Letra trocada** | O OCR lê uma letra ou sílaba como outro caractere, e a palavra deixa de existir. É pior quando a troca produz outra palavra que existe, porque aí nada denuncia o erro | `reunião`, partida no fim da linha, sai como `reuni` / `&o`: o `ão` foi lido como `&o`. 7891/1133 p. 2 (linhas 86–87 do `.txt`) | média, e alta quando a troca produz palavra válida | **Em parte.** Melhorar a imagem (P1) e o idioma (P3) reduz a frequência. Não há correção automática segura da letra trocada: um corretor por dicionário também "corrige" palavras certas, como nomes próprios e termos do autor. O que sobra é revisão humana (§3, ponto 4) |
| **P3 · Idioma errado no OCR** | O OCR usa o vocabulário do idioma informado para decidir entre leituras parecidas. Todo o acervo passou com o pacote de português, inclusive os documentos em outras línguas | Metade do que já foi extraído: **19 itens (20 PDFs)** em inglês, espanhol e francês pelo catálogo. Exemplo: 7891/1134, em espanhol, p. 1. Na amostra o texto saiu legível, mas o ganho de usar o idioma certo ainda não foi medido | média, a conferir | **Sim.** Escolher o idioma do OCR pelo `dc.language.iso` de cada item (`spa`, `eng`, `fra`, ou `por+eng` para material misto). Depende de o catálogo estar certo (§3, ponto 1) |
| **P4 · Palavra partida** | Palavra dividida no fim da linha que continua dividida no `.txt`. Com hífen, o OCR reproduz o hífen. Sem hífen, como já está no original datilografado, as duas metades viram duas "palavras". Nos dois casos a palavra some da busca | Com hífen: `con-` / `tinuidad`, 7891/1134 p. 1. Sem hífen: `socialmen` / `te`, 7891/1133 p. 1 | média | **Sim, com cuidado.** Juntar na extração as duas metades quando a linha termina em hífen e a seguinte começa em minúscula. O risco é colar palavras compostas de verdade (`educador-educando`), por isso precisa de medição antes. Sem hífen, só com dicionário: juntar quando a junção é uma palavra conhecida e as metades não são |
| **P5 · Parágrafo falso** | Linha em branco onde o original não tem quebra de parágrafo, partindo um parágrafo em pedaços. O recorte em trechos usa a linha em branco como fronteira de parágrafo, então cada parágrafo falso é um corte falso | O segundo parágrafo (`Pode parecer…`) é um só na imagem e sai em cerca de sete pedaços. Concentrado no começo do arquivo. 7891/1133 p. 1 | média | **Sim.** Juntar linhas separadas por linha em branco quando a anterior não termina em pontuação final (`.`, `!`, `?`, `:`). O recorte padrão já reagrupa até 2.000 caracteres, o que limita o estrago, mas a correção muda o recorte e precisa de medição |
| **P6 · Ordem de leitura** | Pedaços da página entram fora do lugar: letra capitular ou margem solta no começo das linhas, legenda de foto ou título no meio do parágrafo, colunas misturadas. Típico de revista e jornal A legenda da foto, uma linha contínua no papel, sai em três pedaços intercalados com o subtítulo e o autor: `…la lectura de` / `Una lectura crítica del entorno` / `por Paulo Freire` / `ésta implica la con-`. Mais abaixo, capitular e margem soltas no começo das linhas (`e E parece`, `m acto`). 7891/1134 p. 1. No mesmo documento, colunas misturadas: a frase partida em `La compren-` deveria continuar no alto da coluna da direita, mas o OCR desce para o quadro biográfico abaixo dela (`…sá PAULO FREIRE, famoso pedagogo…`) | média | **Em parte.** O Tesseract tem modos de segmentação da página que podem ajudar em colunas, e isso se mede por tipo de documento. Legenda e capitular dependem do desenho da página, e não há correção geral simples. Para periódicos importantes, a saída é revisão humana. **Com o eScriptorium (§6):** a revisora desenha e divide as regiões (colunas, legenda, quadro) e define a ordem de leitura, e cada região é relida sozinha |
| **P7 · Anotação manuscrita** | Escrita à mão sobre o documento: classificação de arquivo, código, nota na margem, correção. O Tesseract não lê letra de mão, e ela sempre vira letras sem sentido | A anotação a caneta do topo da página (parte, capítulo, série, código do documento e uma letra num círculo) virou `0004 Deveres vVvUVUVvVUUvU VUTU)`. 7891/1133 p. 1. Também em 7891/1134 p. 1: o "D" e o "7" circulados a caneta viraram `o` antes do título e `(&` depois do nome do autor. A mesma marcação de arquivo (letra num círculo) aparece nos dois itens, então deve se repetir na coleção | média | **Não pelo OCR.** Dá para tirar o ruído do texto ou transcrever a anotação à mão. Anotação de arquivo pode ser descartada sem perda, porque a informação já está no catálogo. Nota do autor pode ter valor de acervo (§3, ponto 2). **Com o eScriptorium (§6):** a anotação vira região própria, que fica fora do texto, e um modelo de escrita à mão treinado no acervo pode transcrevê-la |
| **P8 · Ruído de digitalização** | Entra no texto o que não é do documento: o carimbo do Instituto no rodapé (nome, endereço, telefone, e-mail) e os furos de encadernação da margem esquerda, lidos como letras. Como o carimbo se repete em toda página, ele entra em todo trecho indexado e puxa a busca | Carimbo com o e-mail ilegível (`ipf(Opaulofreire.ore`) em **16 páginas de 4 itens**: 7891/1129, 1133, 1134 e 1135. Furos lidos como sequências de `v`, `V` e `U` em 7891/1133 pp. 1–4 (5 linhas) | média | **Sim.** Carimbo: tirar da extração as linhas que se repetem no rodapé de várias páginas do mesmo documento. Furos: limpar a margem antes do OCR (`--clean`, que usa o `unpaper`) ou descartar linhas formadas só por `v`, `V` e `U`. As duas precisam de medição, para não apagar texto legítimo |
| **P10 · Erro sobreposto** | Erro de datilografia do original, às vezes com uma correção a caneta por cima, lido pelo OCR com um segundo erro. O resultado é uma palavra que não está nem no original nem na forma correta. Por isso não se acha comparando com o original, e a forma correta não está em lugar nenhum da página | `ajudará com subsídios` sai como `aguandiá com susídios`: o datiloscrito tem as duas palavras erradas e emendadas a caneta. 7891/1133 p. 4 (linha 197 do `.txt`), perto do fim do arquivo | média, e alta quando o resultado é palavra válida | **Não automaticamente.** Nenhuma ferramenta recupera uma forma que não está escrita na página. Dá para **localizar** os casos: listar as palavras que não estão no dicionário do idioma e conferir à mão. Esse filtro também pega o P2 e o P4, e ajuda a dimensionar a revisão (§3, ponto 3) |
| **P12 · Erro de digitação do original** | O datiloscrito tem uma palavra digitada errada, e o OCR a transcreveu fielmente. O `.txt` está igual ao papel e mesmo assim errado, e quem buscar a forma correta não acha o trecho | `expresão` em lugar de "expressão", igual na imagem. 7891/1133 p. 4 (linha 185 do `.txt`) | média | **Sim, mas é decisão editorial.** Localiza-se pelo mesmo filtro do P10, as palavras fora do dicionário. Corrigir melhora a busca, mas altera a fonte, e o texto citado deixaria de ser o que está no papel (§3, ponto 5) |
| **P9 · Palavras coladas** | Falta o espaço entre duas palavras, quase sempre depois da pontuação. Neste caso vem do original datilografado, não do OCR: o OCR reproduziu fielmente. A busca pode tratar as duas palavras como uma só | `adultos.De` e `parecer,a`: falta espaço depois do ponto e da vírgula. 7891/1133 p. 1 | baixa | **Sim.** Inserir o espaço quando a pontuação vem colada a uma letra (`.De` → `. De`, `,a` → `, a`). Precisa poupar o que não é erro: números (`3.5`), siglas (`U.S.A.`), e-mails e endereços |

Categorias ainda sem ocorrência, para quando aparecerem: **página fora de ordem ou contada
errado** e **metadado divergente** (o catálogo diz uma coisa e o documento mostra outra: ano,
título, idioma).

---

## 3. Para a reunião

Pontos que pedem decisão de quem não é da equipe técnica.

1. **Documentos em outro idioma (P3).** Metade do que já foi extraído não está em português.
   Usar o idioma do catálogo no OCR é decisão técnica. Fica para a curadoria dizer se o
   `dc.language.iso` é confiável o bastante para isso, e para o comitê dizer se texto em outra
   língua entra no sistema do mesmo jeito que o português.
2. **Anotações manuscritas (P7).** Anotação de arquivo pode ser descartada sem perda. Nota do
   próprio autor na margem pode ter valor de acervo, e aí a pergunta é se alguém a transcreve.
   Quem decide é a curadoria, e convém saber antes com que frequência cada tipo aparece.
3. **Quanto revisar (§11.9 do esquema).** O plano sugere 5% das páginas. Este registro dá a base
   para confirmar ou ajustar esse número por coleção, e para fixar a taxa de erro que manda uma
   coleção de volta ao OCR. O P1 mostra que uma conferência automática, a das páginas que saem
   quase vazias, pega o pior caso sem revisão humana nenhuma.
4. **Corrigir à mão ou só registrar (P2).** Quando um problema de gravidade alta aparecer,
   corrige-se o `.txt` à mão, refaz-se o OCR com outro ajuste (como no P1) ou deixa-se o documento
   fora até decidir? Correção à mão some na próxima extração, a menos que se guarde à parte.
5. **Corrigir os erros do original (P12, P10).** Corrigir `expresão` para "expressão" faz a busca
   achar o trecho, mas a citação deixa de reproduzir o documento como ele é. Um meio-termo é
   guardar as duas formas: a do papel, para citar, e a corrigida, só para a busca. Quem decide o
   que vale para a citação é a curadoria e o comitê. O mesmo vale para um corretor ortográfico
   automático: ele acerta erros de OCR, mas também "corrige" grafias de época (`Porisso`,
   `contacto`), nomes próprios e termos do autor. Se entrar, que seja só na forma usada pela
   busca, nunca no texto citado ([roadmap](../roadmap.md) §4, item 9). Na prática de arquivo são a edição
   **diplomática** (preserva o original) e a **normalizada** (corrige), e projetos de acervo
   costumam guardar as duas (§4).
6. **Nível de acabamento por coleção (§4).** Toda coleção precisa de texto revisado, ou parte
   delas serve só para a busca, com o OCR sem revisão? Isso decide o tamanho do trabalho de
   revisão mais do que qualquer ferramenta.
7. **Quem revisa.** Revisão assistida é trabalho humano, página a página. Quem faz, com que
   tempo, e quem confere a revisão?
8. **Voltar à digitalização.** Página com fundo cinza, curvatura ou baixa resolução (P1, P11)
   sai melhor redigitalizada do que corrigida depois. Os originais físicos estão acessíveis para
   isso, e há equipamento?
9. **Nuvem.** As ferramentas mais fortes em manuscrito (P7) rodam na nuvem, e a
   [diretriz 5.2](../diretrizes.md) proíbe material restrito em infraestrutura de terceiros. Há
   coleções que a direção liberaria?

---

## 4. Como o OCR profissional trata esses problemas

Contexto para os pontos do §3. Resume a prática de arquivos, bibliotecas e empresas, sem
nenhuma ferramenta testada aqui.

**OCR profissional é uma linha de produção, não um programa.** A máquina faz o grosso, e a
revisão humana entra onde a própria máquina indica dúvida. As etapas:

1. **Captura.** Digitalização padronizada, seguindo normas como FADGI (EUA) e Metamorfoze
   (Holanda): 300–400 dpi, cor calibrada, cartão de referência na imagem e scanner de livro para
   material encadernado, para o papel não curvar perto da lombada. Página ruim é redigitalizada,
   não consertada depois.
2. **Pré-processamento.** Endireitar a página, desfazer a curvatura, recortar as bordas e separar
   tinta de fundo de forma adaptativa, por região da página.
3. **Análise de layout.** Antes de ler, o sistema desenha **regiões** com tipo (texto, título,
   legenda, foto, carimbo, manuscrito), **linhas** e a **ordem de leitura**. Nas ferramentas
   profissionais isso é **visível e editável**: a pessoa corrige as caixas e a ordem.
4. **Reconhecimento.** Um modelo para cada tipo de material. Manuscrito tem motor próprio (HTR,
   reconhecimento de escrita à mão). Instituições grandes **treinam o modelo no próprio acervo**:
   algumas dezenas de páginas transcritas já melhoram muito o resultado em datilografia de época.
5. **Confiança por palavra.** O motor diz o quanto tem certeza de cada palavra. A revisão
   assistida mostra imagem e texto lado a lado e pula de dúvida em dúvida (baixa confiança, fora
   do dicionário), em vez de ler tudo.
6. **Saída com coordenadas.** O padrão é ALTO XML (Library of Congress), PAGE XML ou hOCR, em que
   cada palavra guarda a posição na imagem e a confiança. Com isso dá para destacar na imagem o
   trecho citado e refazer uma região só. O `.txt` do nosso pipeline perde essa informação.
7. **Controle de qualidade.** Taxa de erro por caractere e por palavra, medida por amostragem
   contra uma transcrição de referência. Contratos de digitalização costumam fixar metas na faixa
   de 99% de acerto por caractere em impresso limpo. E há **níveis de acabamento**: OCR sem
   revisão para busca, e texto revisado só para o que é prioritário ou vai ser citado.
8. **Preservação.** O original e a imagem são a fonte, e o texto é derivado. As correções ficam
   numa camada à parte e versionada, o que resolve o problema do §3, ponto 4.

**Ferramentas de referência:**

| Ferramenta | Perfil | Observação |
|---|---|---|
| ABBYY FineReader / Recognition Server | Empresas, arquivos, governo | Comercial. Referência em impresso, com boa tela de verificação |
| Transkribus | Arquivos e universidades | Forte em manuscrito e em treinar modelo no acervo. **Nuvem** |
| eScriptorium (motor Kraken) | Pesquisa em humanidades | Livre e local. Edita layout e ordem de leitura e treina modelos |
| OCR4all | Pesquisa em humanidades | Livre e local, com fluxo completo e editor de layout |
| Google Document AI, AWS Textract, Azure | Empresas | Nuvem, voltados a documentos comerciais |
| Modelos de visão e linguagem (Docling, olmOCR, Mistral OCR, Qwen-VL) | Recente | Acertam muito melhor a ordem de leitura, mas podem **inventar** texto plausível onde a imagem é ruim, e esse erro não tem cara de erro |

**Onde estão os problemas deste registro:**

| Etapa | Problemas |
|---|---|
| Captura | P1, P8 (furos), P11 |
| Layout | P5, P6, P8 (carimbo, que seria uma região descartada), P11 |
| Reconhecimento | P2, P3, P7, P10 |
| Documento original | P4 (sem hífen), P9, P12 |

O pipeline atual cobre parte do pré-processamento e um reconhecimento genérico. Não tem análise
de layout revisável, confiança por palavra, saída com coordenadas, tela de revisão, modelo
treinado no acervo nem medição de taxa de erro.

---

## 5. Estratégia para o nosso caso

Não dá para redigitalizar, nem para chegar à taxa de erro de um arquivo profissional. A estratégia
parte disso.

1. **O RAG precisa de menos que um arquivo.** Precisa achar o trecho certo e citar a página
   certa, para que a pessoa confira no PDF original pelo handle. A busca por significado tolera
   bastante letra trocada, e a imagem continua sendo a fonte.
2. **Prioridade pelo impacto na busca, não pela contagem de erros.** Pesam muito: página perdida
   (P1), linhas embaralhadas (P11), carimbo repetido (P8) e idioma (P3). Pesam pouco: letra
   trocada ocasional (P2), palavra partida (P4), palavras coladas (P9), erro de digitação do
   original (P12).
3. **Melhorar a partir das imagens que existem:** binarização adaptativa nas páginas ruins,
   idioma pelo catálogo e limpezas depois do OCR. Tudo automático e local.
4. **Medir a nossa taxa de erro**, mesmo sem meta profissional:
   - uma nota automática por página (confiança média e palavras fora do dicionário);
   - uma amostra transcrita à mão, para calcular a taxa real e conferir se a nota acompanha.

   A meta sai desses números, não de contrato de digitalização.
5. **Revisão humana só onde rende:** as piores páginas, que a nota aponta, e os documentos
   prioritários, que o comitê escolhe. O resto fica com o OCR sem revisão, só para busca.
6. **Marcar o que não tem contorno.** Manuscrito (P7), erro sobreposto (P10) e parte do
   embaralhamento (P11) não se resolvem sem uma pessoa. Esses trechos ficam marcados como de
   baixa qualidade, para o sistema e para quem lê a resposta.

## 6. Ferramenta de revisão: eScriptorium

**Decisão (2026-10-23).** A revisão usa o **eScriptorium**, uma plataforma livre de transcrição
de documentos históricos, rodando localmente. O motivo é o 7891/1134: colunas, legenda e quadro
biográfico misturados só se consertam **desenhando e dividindo regiões** na imagem. Uma tela
própria mínima faria só o básico, e o eScriptorium já faz isso e mais:

- desenha e divide regiões e linhas;
- define a ordem de leitura;
- edita a transcrição ao lado da imagem;
- treina modelos de reconhecimento no próprio acervo, inclusive para manuscrito (P7);
- aceita várias revisoras.

O motor dele é o **Kraken**, que segmenta pela linha de base de cada linha, mesmo curva ou
inclinada (P11).

**Fluxo.** Este repositório continua sendo a fonte da verdade, e `main.py` a porta única:

1. `main.py revisao enviar` manda ao eScriptorium os documentos de pior nota, com as imagens e o
   OCR inicial;
2. a revisora corrige lá;
3. `main.py revisao baixar` traz o resultado revisado (PAGE XML) para `data/texto_acervo/`, e o
   texto que o RAG usa é regerado dele.

O que está **só** no eScriptorium não chega ao sistema: revisão não baixada é revisão perdida para
o RAG.

**Ciclo de treino.** Corrige-se algumas dezenas de páginas de uma coleção homogênea, treina-se o
modelo do Kraken com elas, aplica-se ao resto da coleção e se corrige o que sobrar. É onde mais se
ganha em datiloscritos do mesmo período.

**Custos:**

- é um serviço pesado (aplicação web, banco de dados, fila de tarefas), a mais além do Qdrant e
  do Ollama;
- as revisões ficam no banco dele até serem baixadas;
- o treino é mais rápido em GPU, e a placa AMD desta máquina não é a configuração padrão dele.
  Começa-se pela CPU, que leva horas e cabe numa noite.

**Kraken desde o começo (decisão de 2026-10-29).** O Kraken é o motor-alvo também da extração
inicial, não só da revisão. Assim, o modelo treinado no eScriptorium com as páginas corrigidas
volta direto para o OCR de todo o acervo. Até a medição, o melhor caminho medido é o Tesseract com
Sauvola de reserva.

**Estado:** primeiro se mede se o Kraken e as outras variantes de OCR trazem resultado melhor que
o atual. Essa medição é o portão das demais fases, descritas no [roadmap](../roadmap.md) §4,
item 7.
