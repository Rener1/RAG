"""
Cliente da API MediaWiki da UESP.

Fica em `clientes/` e não em `etapas/` porque é adaptador de serviço externo,
como o Ollama e o Qdrant: a etapa de download orquestra, este arquivo fala com
a rede. A separação é o que permite testar a etapa inteira sem rede, injetando
um coletor de mentira.

Uso do conteúdo: a UESP publica sob CC BY-SA. Para uso além de teste local,
conferir https://en.uesp.net/wiki/UESPWiki:Copyright.

Duas decisões de eficiência, mantidas da primeira versão do projeto:

- `prop=revisions` em lote de 50 títulos, em vez de `prop=extracts` (que atende
  uma página por requisição quando se quer o texto completo). Vem wikitext
  bruto, limpo localmente com mwparserfromhell — nenhuma requisição a mais.
- Requisições de lote em paralelo, porque o gargalo é espera de rede.
"""

import requests

from ..config import ConfigDownload
from ..erros import ErroConexao
from .http import criar_sessao


class ColetorUESP:
    """Cliente da API MediaWiki da UESP, no que o pipeline precisa dela."""

    def __init__(self, config: ConfigDownload) -> None:
        self._config = config
        self._sessao = criar_sessao(
            conexoes_simultaneas=max(8, config.lotes_paralelos * 2),
            user_agent=config.user_agent,
        )

    def _consultar(self, parametros: dict) -> dict:
        try:
            resposta = self._sessao.get(
                self._config.api_url,
                params={**parametros, "format": "json"},
                timeout=self._config.timeout,
            )
            resposta.raise_for_status()
            return resposta.json()
        except requests.RequestException as erro:
            raise ErroConexao(
                f"Falha ao consultar a API da UESP: {erro}",
                sugestao="Confira a conexão de rede. O download repete automaticamente erro transitório.",
            ) from erro

    def descobrir_namespace(self) -> int:
        """Id numérico do namespace configurado — a API pede o número, não o nome."""
        dados = self._consultar({"action": "query", "meta": "siteinfo", "siprop": "namespaces"})
        for ns_id, info in dados["query"]["namespaces"].items():
            if self._config.namespace in (info.get("*"), info.get("canonical")):
                return int(ns_id)
        raise ErroConexao(f"Namespace '{self._config.namespace}' não encontrado na wiki.")

    def listar_titulos(self, namespace_id: int, limite: int) -> list[str]:
        """Títulos do namespace, paginando até o limite.

        `apfilterredir=nonredirects` exclui redirects já na origem: eles não
        têm conteúdo próprio e seriam descartados depois de baixados de
        qualquer forma — filtrar aqui economiza requisição e banda.
        """
        titulos: list[str] = []
        continuacao: str | None = None

        while len(titulos) < limite:
            parametros = {
                "action": "query",
                "list": "allpages",
                "apnamespace": namespace_id,
                "apfilterredir": "nonredirects",
                "aplimit": min(500, limite - len(titulos)),
            }
            if continuacao:
                parametros["apcontinue"] = continuacao

            dados = self._consultar(parametros)
            paginas = dados.get("query", {}).get("allpages", [])
            titulos.extend(p["title"] for p in paginas)

            continuacao = dados.get("continue", {}).get("apcontinue")
            if not continuacao or not paginas:
                break

        return titulos[:limite]

    def baixar_lote(self, titulos: list[str]) -> dict[str, str]:
        """Uma requisição, até 50 páginas de wikitext bruto."""
        dados = self._consultar(
            {
                "action": "query",
                "prop": "revisions",
                "rvprop": "content",
                "rvslots": "main",
                "titles": "|".join(titulos),
            }
        )
        paginas = dados.get("query", {}).get("pages", {})

        resultado = {}
        for pagina in paginas.values():
            revisoes = pagina.get("revisions")
            if not revisoes:
                continue  # página inexistente ou apagada
            resultado[pagina["title"]] = revisoes[0].get("slots", {}).get("main", {}).get("*", "")
        return resultado
