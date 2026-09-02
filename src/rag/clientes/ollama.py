"""
Cliente do Ollama — embedding e geração.

Uma classe por papel (`ClienteOllama` embute, `GeradorOllama` gera) porque as
etapas dependem de papéis diferentes: a indexação não deve receber, junto, a
capacidade de gerar texto. Cada uma cumpre um dos protocolos em
`rag.protocolos`.
"""

import json
from collections.abc import Iterator

import requests

from ..config import ConfigEmbedding, ConfigGeracao
from ..erros import ErroConexao
from .http import criar_sessao


class ClienteOllama:
    """Embutidor: texto → vetor, via `/api/embed`."""

    def __init__(self, config: ConfigEmbedding) -> None:
        self._config = config
        self._sessao = criar_sessao(conexoes_simultaneas=max(8, config.lotes_paralelos * 2))

    @property
    def dimensao(self) -> int:
        return self._config.dimensao

    @property
    def modelo(self) -> str:
        return self._config.modelo

    def embutir(self, textos: list[str]) -> list[list[float]]:
        """Vetoriza um lote. Devolve os vetores na ordem dos textos.

        A conferência de contagem existe porque o desalinhamento silencioso é
        o pior erro possível aqui: se o Ollama devolvesse menos vetores que
        textos, o `zip` original casaria cada vetor com o chunk errado e o
        índice ficaria embaralhado sem nenhum sintoma visível.
        """
        if not textos:
            return []

        try:
            resposta = self._sessao.post(
                f"{self._config.ollama_url}/api/embed",
                json={"model": self._config.modelo, "input": textos},
                timeout=self._config.timeout,
            )
            resposta.raise_for_status()
        except requests.RequestException as erro:
            raise ErroConexao(
                f"Falha ao gerar embeddings no Ollama: {erro}",
                sugestao=f"Confira se o Ollama está de pé e se `ollama pull {self._config.modelo}` já foi feito.",
            ) from erro

        vetores = resposta.json().get("embeddings", [])

        if len(vetores) != len(textos):
            raise ErroConexao(
                f"O Ollama devolveu {len(vetores)} vetores para {len(textos)} textos.",
                sugestao="Lote descartado em vez de indexado torto. Reduza `embedding.tamanho_lote` e repita.",
            )

        return vetores

    def esta_disponivel(self) -> tuple[bool, str]:
        """Diagnóstico: (disponível, detalhe legível). Nunca levanta exceção."""
        try:
            resposta = self._sessao.get(f"{self._config.ollama_url}/api/tags", timeout=5)
            resposta.raise_for_status()
        except requests.RequestException as erro:
            return False, str(erro)
        modelos = [m["name"] for m in resposta.json().get("models", [])]
        return True, ", ".join(modelos) if modelos else "nenhum modelo baixado"

    def modelos_baixados(self) -> list[str]:
        disponivel, detalhe = self.esta_disponivel()
        return detalhe.split(", ") if disponivel else []


class GeradorOllama:
    """Gerador: prompt → texto, via `/api/generate`.

    Gera em streaming por padrão. O modo antigo (esperar a resposta inteira)
    deixava o usuário olhando pra um cursor parado por cerca de um minuto sem
    nenhum sinal de que algo estava acontecendo.
    """

    def __init__(self, config: ConfigGeracao) -> None:
        self._config = config
        self._sessao = criar_sessao(tentativas=1)  # geração é cara: não repetir automaticamente

    @property
    def modelo(self) -> str:
        return self._config.modelo

    def gerar(self, prompt: str) -> Iterator[str]:
        """Devolve a resposta em pedaços, na ordem em que o modelo produz."""
        corpo = {
            "model": self._config.modelo,
            "prompt": prompt,
            "stream": self._config.streaming,
            "options": {
                "temperature": self._config.temperatura,
                "num_ctx": self._config.num_ctx,
            },
        }

        try:
            resposta = self._sessao.post(
                f"{self._config.ollama_url}/api/generate",
                json=corpo,
                timeout=self._config.timeout,
                stream=self._config.streaming,
            )
            resposta.raise_for_status()

            if not self._config.streaming:
                yield resposta.json().get("response", "")
                return

            for linha in resposta.iter_lines():
                if not linha:
                    continue
                evento = json.loads(linha)
                if pedaco := evento.get("response"):
                    yield pedaco
                if evento.get("done"):
                    break
        except requests.RequestException as erro:
            raise ErroConexao(
                f"Falha ao gerar resposta no Ollama: {erro}",
                sugestao=f"Confira o Ollama e `ollama pull {self._config.modelo}`.",
            ) from erro
