"""
Cliente do reordenador — cross-encoder local.

A busca vetorial compara dois vetores calculados em separado, cada um sem saber
do outro. Um cross-encoder lê pergunta e trecho **juntos** e julga a relevância
com muito mais informação — em troca, não dá para pré-calcular nada, o que o
limita a reordenar um punhado de candidatos em vez de varrer o acervo. Daí o
desenho de dois estágios: a busca vetorial traz 50, o reordenador escolhe.

Onde ele roda muda tudo. Medidos os mesmos 50 pares: **7,1 s em CPU, 2,38 s em
GPU com fp32 e 0,13 s em GPU com fp16** — a meia precisão vale 18× porque a
RDNA4 tem fp16 rápida e fp32 comparativamente lenta. Em CPU o reranking é caro
demais para uso interativo; na GPU com fp16, é imperceptível. Por isso o padrão
é "auto" nos dois: usa a GPU quando ela existe, e meia precisão quando é GPU.

O `torch` é importado só quando o modelo é de fato carregado, não na importação
do módulo: quem roda `chunking` ou `config` não deve pagar alguns segundos de
carga de biblioteca por uma capacidade que não vai usar.
"""

from functools import cached_property

from ..config import ConfigReordenacao
from ..erros import ErroPreRequisito
from ..modelos import TrechoRecuperado


class ReordenadorLocal:
    """Cumpre `Reordenador` com um cross-encoder rodando na máquina."""

    def __init__(self, config: ConfigReordenacao) -> None:
        self._config = config

    @cached_property
    def _dispositivo(self) -> str:
        """Onde rodar. "auto" prefere a GPU e cai para CPU sem reclamar."""
        if self._config.dispositivo != "auto":
            return self._config.dispositivo
        try:
            import torch

            return "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            return "cpu"

    @cached_property
    def _modelo(self):
        """Carrega tokenizador e modelo na primeira vez que forem precisos."""
        try:
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
        except ImportError as erro:
            raise ErroPreRequisito(
                f"Reordenação pedida, mas falta uma dependência: {erro.name}.",
                sugestao="Instale com `pip3 install -r requirements.txt`, ou desligue com `--sem-reordenar`.",
            ) from erro

        dispositivo = self._dispositivo
        if self._config.precisao == "fp16":
            tipo = torch.float16
        elif self._config.precisao == "fp32":
            tipo = torch.float32
        else:
            # Meia precisão só na GPU: em CPU ela é mais lenta ou não suportada.
            tipo = torch.float16 if dispositivo.startswith("cuda") else torch.float32

        try:
            tokenizador = AutoTokenizer.from_pretrained(self._config.modelo)
            modelo = AutoModelForSequenceClassification.from_pretrained(self._config.modelo, dtype=tipo)
        except OSError as erro:
            raise ErroPreRequisito(
                f"Não foi possível carregar o modelo de reordenação '{self._config.modelo}'.",
                sugestao=(
                    "Na primeira vez ele é baixado do Hugging Face e precisa de rede. "
                    "Com a máquina offline, desligue a reordenação com `--sem-reordenar`."
                ),
            ) from erro

        modelo.to(dispositivo)
        modelo.eval()
        return torch, tokenizador, modelo

    @property
    def modelo(self) -> str:
        return self._config.modelo

    def esta_disponivel(self) -> tuple[bool, str]:
        """Diagnóstico para `main.py ambiente`. Nunca levanta exceção."""
        try:
            _ = self._modelo
        except ErroPreRequisito as erro:
            return False, erro.mensagem
        return True, f"{self._config.modelo} em {self._dispositivo}"

    def reordenar(self, pergunta: str, trechos: list[TrechoRecuperado]) -> list[TrechoRecuperado]:
        """Os mesmos trechos, do mais para o menos relevante segundo o modelo.

        O `score` de cada trecho é preservado como veio da busca vetorial. O
        cross-encoder produz uma pontuação em outra escala, que não é comparável
        com cosseno e não diria nada a quem lê a saída de `buscar` — quem carrega
        a decisão dele é a ordem.
        """
        if not trechos:
            return []

        torch, tokenizador, modelo = self._modelo

        # Lotear por tamanho parecido, e não na ordem de chegada. O lote é
        # preenchido até o comprimento do maior item dele, então misturar um
        # trecho de 60 caracteres com um de 1900 faz o modelo processar
        # preenchimento em vez de texto. Medido nos 50 candidatos de uma pergunta
        # real: 13,8 s desordenado contra 7,1 s ordenado, com resultado idêntico.
        ordem = sorted(range(len(trechos)), key=lambda i: len(trechos[i].texto))
        notas = [0.0] * len(trechos)

        for inicio in range(0, len(ordem), self._config.tamanho_lote):
            indices = ordem[inicio : inicio + self._config.tamanho_lote]
            entradas = tokenizador(
                [pergunta] * len(indices),
                [trechos[i].texto for i in indices],
                padding=True,
                truncation=True,
                max_length=self._config.tamanho_maximo,
                return_tensors="pt",
            ).to(self._dispositivo)

            with torch.no_grad():
                saida = modelo(**entradas).logits.view(-1).float()
            for i, nota in zip(indices, saida.tolist(), strict=True):
                notas[i] = nota

        # Empate desfeito pelo `chunk_id`, para a ordem não variar entre rodadas
        # e a avaliação continuar comparável.
        pares = sorted(zip(trechos, notas, strict=True), key=lambda par: (-par[1], par[0].chunk_id))
        return [trecho for trecho, _ in pares]
