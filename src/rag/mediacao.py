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
from .modelos import TrechoRecuperado
from .protocolos import Gerador, RecuperadorDeTrechos

# Numeração e marcador de lista que o modelo põe mesmo quando se pede que não ponha.
PADRAO_MARCADOR = re.compile(r"^\s*(?:\d+[.)\]]|[-*•–—])\s*")

# Linhas em que o modelo comenta a tarefa em vez de executá-la.
ECOS_DO_PROMPT = ("sub-consulta", "subconsulta", "consultas:", "pergunta original", "aqui estão", "claro,")

TAMANHO_MINIMO_DE_SUBCONSULTA = 8
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

    @property
    def houve_decomposicao(self) -> bool:
        return self.veio_do_modelo and len(self.subconsultas) > 1


def montar_prompt_de_decomposicao(pergunta: str, maximo: int, orientacao: str = "") -> str:
    """Prompt da reformulação. `orientacao` vem da seção do marco.

    O marco entra aqui porque buscar posições divergentes é decisão pedagógica,
    não parâmetro de ranking: é no marco que o comitê escreve, por exemplo, que
    uma das buscas deve procurar a posição contrária.
    """
    extra = f"\n\nOrientação adicional:\n{orientacao}" if orientacao.strip() else ""

    return f"""Você prepara buscas em um acervo de documentos.

Reescreva a pergunta abaixo como até {maximo} consultas de busca independentes, \
cada uma cobrindo um aspecto diferente do que foi perguntado.

Regras:
- Uma consulta por linha, e nada mais na resposta.
- Sem numeração, sem marcador, sem explicação, sem introdução.
- Cada consulta se sustenta sozinha, sem depender das outras para fazer sentido.
- Mantenha o idioma da pergunta original.
- Se a pergunta já for simples e direta, devolva uma linha só.{extra}

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
        config: ConfigIntermediacao,
        config_busca: ConfigBusca,
        ao_decompor: Callable[[ConsultaDecomposta], None] = lambda consulta: None,
        orientacao_do_marco: str = "",
    ) -> None:
        self._recuperador = recuperador
        self._gerador = gerador
        self._config = config
        self._config_busca = config_busca
        self._ao_decompor = ao_decompor
        self._orientacao = orientacao_do_marco

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

        if len(pergunta.strip()) < self._config.minimo_de_caracteres:
            return self._sem_decomposicao(pergunta, "pergunta curta demais para valer uma reformulação")

        prompt = montar_prompt_de_decomposicao(pergunta, self._config.maximo_de_subconsultas, self._orientacao)
        try:
            saida = "".join(self._gerador.gerar(prompt))
        except ErroPipeline as erro:
            return self._sem_decomposicao(pergunta, f"o modelo não respondeu ({erro.mensagem})")

        subconsultas = extrair_subconsultas(saida, self._config.maximo_de_subconsultas, pergunta)
        if not subconsultas:
            return self._sem_decomposicao(pergunta, "o modelo não devolveu sub-consultas legíveis")

        if self._config.incluir_pergunta_original:
            subconsultas = [pergunta, *subconsultas]

        return ConsultaDecomposta(original=pergunta, subconsultas=subconsultas, veio_do_modelo=True)

    def buscar(self, pergunta: str, k: int | None = None) -> list[TrechoRecuperado]:
        consulta = self.decompor(pergunta)
        self._ao_decompor(consulta)

        # Uma consulta só é o caminho de sempre, com o mesmo k: o fallback tem
        # de ser indistinguível da busca direta, senão desligar a mediação
        # deixaria de ser uma comparação limpa.
        if len(consulta.subconsultas) == 1:
            return self._recuperador.buscar(consulta.subconsultas[0], k=k)

        rankings = [
            self._recuperador.buscar(subconsulta, k=self._config.k_por_subconsulta)
            for subconsulta in consulta.subconsultas
        ]

        fundidos = fundir_por_rrf(rankings, self._config.constante_rrf)
        fundidos = limitar_por_documento(fundidos, self._config.diversidade_por_documento)
        return fundidos[: k or self._config_busca.k]
