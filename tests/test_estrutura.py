"""
As regras estruturais do projeto, mecanizadas.

`CLAUDE.md` declara duas regras e diz que são verificáveis com `grep`. Grep é
verificação que alguém precisa lembrar de rodar. Aqui elas viram teste, que roda
sozinho junto com o resto da suíte.

Regra 1 — nenhum módulo de `etapas/` importa outro módulo de `etapas/`. É o que
permite refazer uma etapa sem afetar as outras: elas se comunicam por artefato
em disco, não por chamada de função.

Regra 2 — as etapas dependem de `protocolos.py`, nunca de `clientes/`. É o que
permite trocar o banco vetorial escrevendo outra classe com os mesmos métodos, e
é o que permite estes testes rodarem sem Qdrant nem Ollama.
"""

import ast
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
PASTA_ETAPAS = RAIZ / "src" / "rag" / "etapas"

# Módulos que compõem etapas com geração — o lugar deles é a raiz do pacote,
# ao lado de `orquestrador.py`, pelo motivo que o cabeçalho dele explica.
MODULOS_DE_COMPOSICAO = ("marco.py", "mediacao.py", "sessao.py")


def _modulos_de_etapa() -> set[str]:
    return {caminho.stem for caminho in PASTA_ETAPAS.glob("*.py") if caminho.stem != "__init__"}


def _importacoes(caminho: Path) -> list[tuple[int, int, str]]:
    """(linha, nível relativo, módulo) de cada import do arquivo.

    Nível 0 é import absoluto; 1 é `from .x`; 2 é `from ..x`. O módulo vem
    vazio em `from . import nome`, que é importar do `__init__` do próprio
    pacote — permitido, é de onde vem o contrato de progresso.
    """
    arvore = ast.parse(caminho.read_text(encoding="utf-8"), filename=str(caminho))
    encontradas: list[tuple[int, int, str]] = []

    for no in ast.walk(arvore):
        if isinstance(no, ast.ImportFrom):
            encontradas.append((no.lineno, no.level, no.module or ""))
        elif isinstance(no, ast.Import):
            encontradas.extend((no.lineno, 0, alias.name) for alias in no.names)

    return encontradas


class TestRegrasDasEtapas(unittest.TestCase):
    def test_nenhuma_etapa_importa_outra_etapa(self):
        etapas = _modulos_de_etapa()
        self.assertTrue(etapas, "nenhum módulo encontrado em etapas/ — caminho errado?")

        for caminho in sorted(PASTA_ETAPAS.glob("*.py")):
            for linha, nivel, modulo in _importacoes(caminho):
                # `from .x import ...` dentro de etapas/ aponta para um irmão.
                if nivel == 1 and modulo.split(".")[0] in etapas:
                    self.fail(
                        f"{caminho.name}:{linha} importa a etapa '{modulo}'. "
                        "As etapas se comunicam por artefato em disco, não por import — "
                        "esse código pertence a orquestrador.py ou a um módulo de composição na raiz."
                    )

    def test_nenhuma_etapa_importa_clientes(self):
        for caminho in sorted(PASTA_ETAPAS.glob("*.py")):
            for linha, _, modulo in _importacoes(caminho):
                if "clientes" in modulo.split("."):
                    self.fail(
                        f"{caminho.name}:{linha} importa '{modulo}'. "
                        "As etapas dependem de protocolos.py, não das implementações concretas."
                    )

    def test_modulos_de_composicao_ficam_fora_de_etapas(self):
        for nome in MODULOS_DE_COMPOSICAO:
            self.assertFalse(
                (PASTA_ETAPAS / nome).exists(),
                f"{nome} está em etapas/. Ele compõe recuperação com geração, então precisaria "
                "importar duas etapas — o lugar dele é src/rag/, ao lado de orquestrador.py.",
            )


if __name__ == "__main__":
    unittest.main()
