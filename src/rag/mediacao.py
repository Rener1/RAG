"""
Intermediação entre a pergunta e o modelo de embedding.

Uma pergunta composta vira um vetor só, e esse vetor fica no meio-termo entre as
partes que a pergunta junta — perto de tudo e específico de nada. Aqui ela é
reformulada e decomposta em sub-consultas, cada uma é buscada em separado, e os
resultados se combinam antes de a resposta ser montada.

Fica na recuperação, e não na geração, porque é decisão de recuperação: dá para
avaliar `recall@k` com e sem, sem gerar uma linha de texto.

Mora na raiz do pacote, ao lado de `orquestrador.py`, pelo motivo que o
cabeçalho dele explica: compõe geração com recuperação, e isso não pertence a
nenhuma das duas etapas. Depende do protocolo `RecuperadorDeTrechos`, nunca da
classe `Recuperador` — é o que permite empilhar as duas coisas sem que o
`MotorRag` saiba que existe uma camada a mais.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from .config import ConfigBusca, ConfigIntermediacao
from .erros import ErroPipeline
from .etapas.recuperacao import recortar_por_limiar_relativo
from .modelos import TrechoRecuperado
from .protocolos import Embutidor, Gerador, RecuperadorDeTrechos, Reordenador

# Numeração e marcador de lista que o modelo põe mesmo quando se pede que não ponha.
PADRAO_MARCADOR = re.compile(r"^\s*(?:\d+[.)\]]|[-*•–—])\s*")

# Linhas em que o modelo comenta a tarefa em vez de executá-la.
ECOS_DO_PROMPT = ("sub-consulta", "subconsulta", "consultas:", "pergunta original", "aqui estão", "claro,")

# Mínimo de caracteres de uma consulta aceitável. Baixo porque nome próprio
# sozinho é consulta legítima quando a pergunta é traduzida ("Lorkhan" tem 7);
# o descarte de fragmento inútil quem faz é o filtro de eco do prompt.
TAMANHO_MINIMO_DE_SUBCONSULTA = 4
TAMANHO_MAXIMO_DE_SUBCONSULTA = 200


@dataclass(frozen=True, slots=True)
class ConsultaDecomposta:
    """O que foi de fato buscado, e por quê.

    `motivo_do_fallback` existe para a interface poder dizer por que não houve
    decomposição. Sem ele, "o modelo caiu" e "a pergunta era curta demais para
    valer a chamada" produziriam exatamente a mesma tela.
    """

    original: str
    subconsultas: list[str] = field(default_factory=list)
    veio_do_modelo: bool = False
    motivo_do_fallback: str = ""
    descartadas_por_redundancia: int = 0

    @property
    def houve_decomposicao(self) -> bool:
        return self.veio_do_modelo and len(self.subconsultas) > 1


# Nomes dos idiomas que o prompt precisa dizer por extenso. Marco que declare
# um código fora daqui cai no próprio código, que o modelo entende igual.
NOMES_DE_IDIOMA = {"en": "inglês", "pt": "português", "es": "espanhol", "fr": "francês"}


def montar_prompt_de_decomposicao(
    pergunta: str,
    maximo: int,
    orientacao: str = "",
    idioma_do_acervo: str = "",
    decompor: bool = True,
) -> str:
    """Prompt que prepara a consulta: traduz para o idioma do acervo e decompõe.

    As duas tarefas vêm juntas porque medem coisas diferentes e ambas rendem.
    Traduzir para o idioma do acervo vale +5 de recall quando pergunta e
    documento estão em línguas diferentes; decompor separa os assuntos de uma
    pergunta composta, que num vetor só ficariam no meio-termo entre eles.

    **Os exemplos não são enfeite.** Sem eles o modelo trata nome próprio como
    palavra traduzível: "o que são os Hist?" virou `histories`, destruindo o
    termo de maior sinal da consulta. E sem "perguntas completas, não palavras
    soltas" ele devolve sopa de palavras-chave, que embute pior que a frase.

    `orientacao` vem da seção `## Decomposição` do marco. É onde o comitê
    escreve o que a busca deve procurar — posição divergente, por exemplo, que é
    decisão pedagógica e não parâmetro de ranking.
    """
    extra = f"\n\nOrientação adicional:\n{orientacao}" if orientacao.strip() else ""

    if idioma_do_acervo:
        nome = NOMES_DE_IDIOMA.get(idioma_do_acervo, idioma_do_acervo)
        traducao = (
            f"1. **Traduza a pergunta para {nome}**, mantendo cada nome próprio "
            "exatamente como está escrito — nomes de povos, lugares, obras, eventos "
            "e criaturas ficam intactos mesmo quando parecem palavras comuns "
            "traduzíveis.\n\n"
        )
        cabecalho = f"Você prepara a busca de uma pergunta num acervo de documentos escritos em {nome}."
        exemplos = """
Exemplos:

  "o que são os Hist?"
  -> what are the Hist?

  "quem foi Lorkhan?"
  -> who was Lorkhan?

  "quem são os argonianos e qual a relação deles com os hist?"
  -> who are the Argonians?
  -> what is the relationship between the Argonians and the Hist?
"""
    else:
        traducao = ""
        cabecalho = "Você prepara a busca de uma pergunta num acervo de documentos."
        exemplos = ""

    if decompor:
        numero = "2." if traducao else "1."
        instrucao = (
            f"{numero} **Se a pergunta juntar assuntos diferentes**, que seriam "
            "procurados em lugares diferentes do acervo, escreva uma linha por "
            "assunto. Se tratar de um assunto só, escreva uma linha só.\n\n"
        )
        limite = f"no máximo {maximo}"
    else:
        instrucao = ""
        limite = "uma linha só"

    return f"""{cabecalho}

{traducao}{instrucao}Escreva perguntas completas, não palavras soltas.
{exemplos}
Responda só com as linhas, {limite}, sem numeração e sem comentário.{extra}

PERGUNTA:
{pergunta}
"""


def extrair_subconsultas(saida_do_modelo: str, maximo: int, pergunta: str) -> list[str]:
    """Linhas da saída do modelo que servem como consulta. Lixo devolve vazio.

    Deliberadamente rígida: uma sub-consulta ruim custa uma busca inteira e
    entra na fusão como se valesse tanto quanto as boas. Descartar e cair na
    pergunta original é melhor do que buscar o comentário do modelo sobre a
    própria tarefa.
    """
    aceitas: list[str] = []
    vistas = {pergunta.strip().casefold()}

    for linha in saida_do_modelo.splitlines():
        texto = PADRAO_MARCADOR.sub("", linha).strip().strip('"').strip()
        if not TAMANHO_MINIMO_DE_SUBCONSULTA <= len(texto) <= TAMANHO_MAXIMO_DE_SUBCONSULTA:
            continue

        comparavel = texto.casefold()
        if comparavel in vistas or any(eco in comparavel for eco in ECOS_DO_PROMPT):
            continue

        vistas.add(comparavel)
        aceitas.append(texto)
        if len(aceitas) >= maximo:
            break

    return aceitas


def similaridade(a: list[float], b: list[float]) -> float:
    """Cosseno entre dois vetores. Zero quando algum deles é nulo."""
    produto = sum(x * y for x, y in zip(a, b, strict=True))
    norma_a = sum(x * x for x in a) ** 0.5
    norma_b = sum(y * y for y in b) ** 0.5
    return 0.0 if norma_a == 0 or norma_b == 0 else produto / (norma_a * norma_b)


def descartar_redundantes(
    consultas: list[str],
    embutidor: Embutidor,
    limiar: float,
) -> tuple[list[str], int]:
    """Remove consultas quase idênticas a outra já aceita.

    **Rede de segurança, não o mecanismo principal.** Quem reduz o número de
    sub-consultas é o prompt, que pede uma linha só quando a pergunta trata de
    um assunto só; isto aqui apara o que escapa.

    O limiar é alto porque a medição não permite outra coisa. Medido com bge-m3
    neste corpus, cosseno entre consultas curtas **não separa** as duas classes:

        redundantes   0,620 ── 0,988
        distintas     0,664 ── 0,893

    "O que diz a lenda do dragonborn?" e "lenda dragonborn" dão 0,620 — abaixo
    de "história dos dragonborn" e "poderes dos dragonborn" (0,664), que são
    facetas legítimas. O embedding codifica forma junto com sentido, e pergunta
    longa contra palavra-chave curta afasta os vetores mesmo quando o assunto é
    o mesmo. Não existe corte que pegue todas as duplicatas sem matar faceta.

    Daí o limiar conservador: descartar uma faceta legítima custa recall, que é
    invisível; manter uma consulta redundante custa uma busca de ~0,1 s, e o RRF
    ainda deduplica os trechos por `chunk_id`. Errar para o lado de conservar é
    o lado barato.

    A ordem manda: a primeira de um par redundante fica. Como a pergunta
    original, quando incluída, é a primeira da lista, ela nunca é descartada.

    Falha do embutidor devolve a lista intacta. A recuperação não pode parar por
    causa de uma otimização.
    """
    if limiar >= 1.0 or len(consultas) < 2:
        return list(consultas), 0

    try:
        vetores = embutidor.embutir(list(consultas))
    except (ErroPipeline, ValueError):
        return list(consultas), 0

    aceitas: list[str] = []
    vetores_aceitos: list[list[float]] = []

    for consulta, vetor in zip(consultas, vetores, strict=True):
        if any(similaridade(vetor, aceito) > limiar for aceito in vetores_aceitos):
            continue
        aceitas.append(consulta)
        vetores_aceitos.append(vetor)

    return aceitas, len(consultas) - len(aceitas)


def fundir_por_rrf(rankings: list[list[TrechoRecuperado]], constante: int = 60) -> list[TrechoRecuperado]:
    """Reciprocal Rank Fusion — combina rankings pela posição, não pelo score.

    Score de cosseno de consultas diferentes não é comparável entre si: somar ou
    tomar o máximo entrega a decisão à sub-consulta que por acaso produziu
    similaridade mais alta, e somar ainda premia o trecho que várias
    sub-consultas parecidas trouxeram — ou seja, premia redundância, que é o
    oposto do que se quer. A posição é comparável por construção.

    Deduplica por `chunk_id`. O `score` devolvido é a melhor similaridade
    original daquele trecho, não a pontuação da fusão: é a ordem que carrega a
    fusão, e assim o número que a interface imprime continua querendo dizer
    "quão perto do vetor", comparável com e sem mediação.
    """
    pontos: dict[str, float] = {}
    melhor: dict[str, TrechoRecuperado] = {}

    for ranking in rankings:
        for posicao, trecho in enumerate(ranking, start=1):
            pontos[trecho.chunk_id] = pontos.get(trecho.chunk_id, 0.0) + 1.0 / (constante + posicao)
            if trecho.chunk_id not in melhor or trecho.score > melhor[trecho.chunk_id].score:
                melhor[trecho.chunk_id] = trecho

    # Empate desfeito pela similaridade e depois pelo id: sem isso a ordem de
    # dois trechos empatados mudaria entre execuções, e comparar duas rodadas
    # de avaliação viraria adivinhação.
    ordenados = sorted(pontos, key=lambda chunk_id: (-pontos[chunk_id], -melhor[chunk_id].score, chunk_id))
    return [melhor[chunk_id] for chunk_id in ordenados]


def limitar_por_documento(trechos: list[TrechoRecuperado], teto: int) -> list[TrechoRecuperado]:
    """Limita quantos trechos do mesmo documento entram no resultado.

    Diversificação pela metade, e é o que dá para fazer sem mudar protocolo:
    diversificar de verdade (MMR) exige os vetores dos trechos recuperados, e
    `RepositorioVetorial.buscar` não os devolve. Isto mata a redundância mais
    grosseira — cinco trechos do mesmo artigo ocupando o contexto inteiro.
    """
    if teto <= 0:
        return list(trechos)

    contagem: dict[str, int] = {}
    resultado: list[TrechoRecuperado] = []

    for trecho in trechos:
        usados = contagem.get(trecho.documento_origem, 0)
        if usados >= teto:
            continue
        contagem[trecho.documento_origem] = usados + 1
        resultado.append(trecho)

    return resultado


class IntermediadorDeConsulta:
    """Cumpre `RecuperadorDeTrechos`, envolvendo outro recuperador.

    Entra por injeção em `servico.py`: nem o `MotorRag` nem as ações da interface
    sabem que existe. Trocar de volta para a busca direta é uma linha lá.
    """

    def __init__(
        self,
        recuperador: RecuperadorDeTrechos,
        gerador: Gerador,
        embutidor: Embutidor,
        config: ConfigIntermediacao,
        config_busca: ConfigBusca,
        ao_decompor: Callable[[ConsultaDecomposta], None] = lambda consulta: None,
        orientacao_do_marco: str = "",
        idioma_do_acervo: str = "",
        reordenador: Reordenador | None = None,
    ) -> None:
        self._recuperador = recuperador
        self._gerador = gerador
        self._embutidor = embutidor
        self._config = config
        self._config_busca = config_busca
        self._ao_decompor = ao_decompor
        self._orientacao = orientacao_do_marco
        self._idioma = idioma_do_acervo
        self._reordenador = reordenador

    def _sem_decomposicao(self, pergunta: str, motivo: str) -> ConsultaDecomposta:
        return ConsultaDecomposta(original=pergunta, subconsultas=[pergunta], motivo_do_fallback=motivo)

    def decompor(self, pergunta: str) -> ConsultaDecomposta:
        """Sub-consultas a buscar. Nunca levanta: qualquer tropeço vira fallback.

        Que a indisponibilidade do modelo de geração não derrube a busca é
        requisito, não conveniência — a recuperação é avaliável sozinha, e
        precisa continuar sendo mesmo com o gerador fora do ar.
        """
        if not self._config.ligada:
            return self._sem_decomposicao(pergunta, "mediação desligada")

        if not self._config.decompor and not self._idioma:
            return self._sem_decomposicao(pergunta, "nada a preparar: sem decomposição nem tradução")

        # A guarda de tamanho vale só quando decompor é o único trabalho:
        # pergunta curta não tem o que decompor, e a chamada seria desperdício.
        # **Traduzir paga em qualquer tamanho** — pergunta curta tem menos termos
        # para casar, que é onde o descasamento de idioma mais custa. Antes desta
        # distinção, "o que são os Hist?" (18 caracteres) pulava o modelo e ia à
        # busca em português contra um acervo em inglês.
        so_decompoe = self._config.decompor and not self._idioma
        if so_decompoe and len(pergunta.strip()) < self._config.minimo_de_caracteres:
            return self._sem_decomposicao(pergunta, "pergunta curta demais para valer uma reformulação")

        prompt = montar_prompt_de_decomposicao(
            pergunta,
            self._config.maximo_de_subconsultas,
            self._orientacao,
            self._idioma,
            self._config.decompor,
        )
        try:
            saida = "".join(self._gerador.gerar(prompt))
        except ErroPipeline as erro:
            return self._sem_decomposicao(pergunta, f"o modelo não respondeu ({erro.mensagem})")

        teto = self._config.maximo_de_subconsultas if self._config.decompor else 1
        subconsultas = extrair_subconsultas(saida, teto, pergunta)
        if not subconsultas:
            return self._sem_decomposicao(pergunta, "o modelo não devolveu consulta legível")

        # A dedup roda entre as saídas do modelo, para tirar paráfrase que ele
        # produziu ao preencher o teto. A pergunta original entra depois.
        subconsultas, descartadas = descartar_redundantes(
            subconsultas, self._embutidor, self._config.limiar_de_redundancia
        )

        if self._config.incluir_pergunta_original:
            # Sem tradução, a original participa da dedup: uma sub-consulta que é
            # só ela reescrita não acrescenta nada e custa uma busca.
            #
            # **Com tradução, não.** O bge-m3 é multilíngue e alinha uma boa
            # tradução quase no mesmo vetor da original — medido, 0,974 entre
            # "o que são os Hist?" e "what are the Hist?", acima do limiar. A
            # dedup mataria justamente a consulta que rende: buscar em inglês
            # vale 90% de recall contra 85% do português, e aqueles 0,026 de
            # diferença de vetor são o ganho inteiro. Paráfrase inútil e tradução
            # útil ficam ambas em ~0,97, e nenhum limiar separa as duas.
            if self._idioma:
                subconsultas = [pergunta, *subconsultas]
            else:
                subconsultas, descartadas_com_original = descartar_redundantes(
                    [pergunta, *subconsultas], self._embutidor, self._config.limiar_de_redundancia
                )
                descartadas += descartadas_com_original

        return ConsultaDecomposta(
            original=pergunta,
            subconsultas=subconsultas,
            veio_do_modelo=True,
            descartadas_por_redundancia=descartadas,
        )

    def buscar(self, pergunta: str, k: int | None = None) -> list[TrechoRecuperado]:
        consulta = self.decompor(pergunta)
        self._ao_decompor(consulta)

        # Uma consulta só é o caminho de sempre, com o mesmo k: o fallback tem
        # de ser indistinguível da busca direta, senão desligar a mediação
        # deixaria de ser uma comparação limpa.
        if len(consulta.subconsultas) == 1:
            return self._recuperador.buscar(consulta.subconsultas[0], k=k)

        # O pool precisa comportar o que a política de quantidade pode pedir:
        # buscar 8 por sub-consulta e depois aplicar uma política com teto 20
        # deixaria a política sem candidatos, e o resultado sairia menor que o da
        # busca direta — que é o oposto do que a fusão deveria fazer.
        por_subconsulta = self._config.k_por_subconsulta
        if k is not None:
            por_subconsulta = max(por_subconsulta, k)
        elif self._config_busca.limiar_relativo > 0:
            por_subconsulta = max(por_subconsulta, self._config_busca.k_maximo)

        rankings = [self._recuperador.buscar(subconsulta, k=por_subconsulta) for subconsulta in consulta.subconsultas]

        fundidos = fundir_por_rrf(rankings, self._config.constante_rrf)
        fundidos = limitar_por_documento(fundidos, self._config.diversidade_por_documento)

        # Reordena **uma vez, sobre a lista fundida**, e não uma vez por
        # sub-consulta. Reordenar por sub-consulta custaria N vezes o mesmo
        # trabalho — com duas consultas e 50 candidatos, cem pares em vez de
        # cinquenta — e cada julgamento seria contra uma sub-consulta em vez de
        # contra o que a pessoa de fato perguntou. Quem julga aqui é a pergunta
        # original, que é o critério certo.
        if self._reordenador is not None:
            try:
                fundidos = self._reordenador.reordenar(
                    pergunta, fundidos[: self._config_busca.candidatos_para_reordenar]
                )
            except (ErroPipeline, RuntimeError, ValueError):
                pass

        # A mesma política de quantidade da busca direta, e não um corte fixo em
        # `config_busca.k`. Cortar diferente aqui faria `avaliar --comparar`
        # medir onze trechos de um lado contra oito do outro, e a comparação
        # deixaria de dizer alguma coisa sobre a mediação.
        if k is not None:
            return fundidos[:k]
        if self._config_busca.limiar_relativo > 0:
            return recortar_por_limiar_relativo(
                fundidos[: self._config_busca.k_maximo],
                self._config_busca.limiar_relativo,
                self._config_busca.k_minimo,
            )
        return fundidos[: self._config_busca.k]
