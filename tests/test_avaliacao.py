"""
O harness de avaliação da recuperação.

A aritmética das métricas é o que decide se uma mudança entra ou sai, então
está conferida à mão em casos pequenos. Um harness com métrica errada é pior que
harness nenhum: dá confiança numerada a uma conclusão falsa.

Só a camada 1 (recuperação). A qualidade da resposta é rubrica humana
(`docs/plano/fase-3-avaliacao-e-servidor.md` §5) e não é medida aqui.
"""

import json
import tempfile
import unittest
from pathlib import Path

from apoio import RecuperadorFalso

from rag.avaliacao import (  # noqa: E402
    CasoDeTeste,
    ResultadoDaAvaliacao,
    ResultadoDeCaso,
    avaliar,
    carregar_casos,
    comparar,
)
from rag.erros import ErroConfiguracao  # noqa: E402
from rag.modelos import TrechoRecuperado  # noqa: E402


def trecho(pagina: str) -> TrechoRecuperado:
    return TrechoRecuperado(
        texto=f"texto de {pagina}",
        titulo_pagina=pagina,
        documento_origem=f"{pagina}.txt",
        chunk_id=f"{pagina}::0",
        score=0.9,
    )


def caso(identificador: str, esperadas: tuple[str, ...], tipo: str = "duvida_factual") -> CasoDeTeste:
    return CasoDeTeste(
        identificador=identificador,
        demanda=f"pergunta {identificador}",
        paginas_esperadas=esperadas,
        tipo_de_demanda=tipo,
    )


def resultado(identificador, esperadas, recuperadas, tipo="duvida_factual") -> ResultadoDeCaso:
    return ResultadoDeCaso(caso=caso(identificador, esperadas, tipo), paginas_recuperadas=recuperadas)


def gravar(linhas: list[str]) -> Path:
    arquivo = Path(tempfile.mkdtemp()) / "casos.jsonl"
    arquivo.write_text("\n".join(linhas), encoding="utf-8")
    return arquivo


class TestMetricasDeUmCaso(unittest.TestCase):
    def test_acerto_na_primeira_posicao(self):
        r = resultado("a", ("Lore:Hist",), ("Lore:Hist", "Lore:Outro"))
        self.assertTrue(r.acertou)
        self.assertEqual(r.acertos, 1)
        self.assertEqual(r.posicao_do_primeiro_acerto, 1)
        self.assertEqual(r.cobertura, 1.0)

    def test_acerto_no_meio_da_lista(self):
        r = resultado("a", ("Lore:Hist",), ("Lore:X", "Lore:Y", "Lore:Hist"))
        self.assertEqual(r.posicao_do_primeiro_acerto, 3)

    def test_sem_acerto_nenhum(self):
        r = resultado("a", ("Lore:Hist",), ("Lore:X", "Lore:Y"))
        self.assertFalse(r.acertou)
        self.assertIsNone(r.posicao_do_primeiro_acerto)
        self.assertEqual(r.cobertura, 0.0)

    def test_cobertura_parcial(self):
        """Achar uma de três é acerto no recall e um terço na cobertura."""
        r = resultado("a", ("Lore:A", "Lore:B", "Lore:C"), ("Lore:A", "Lore:Z"))
        self.assertTrue(r.acertou)
        self.assertAlmostEqual(r.cobertura, 1 / 3)

    def test_a_posicao_e_a_da_primeira_esperada_e_nao_a_da_melhor(self):
        r = resultado("a", ("Lore:A", "Lore:B"), ("Lore:B", "Lore:A"))
        self.assertEqual(r.posicao_do_primeiro_acerto, 1)
        self.assertEqual(r.acertos, 2)


class TestMetricasAgregadas(unittest.TestCase):
    def _avaliacao(self, resultados) -> ResultadoDaAvaliacao:
        return ResultadoDaAvaliacao(resultados=resultados, k=5, segundos=0.0)

    def test_recall_e_a_fracao_de_casos_com_algum_acerto(self):
        a = self._avaliacao(
            [
                resultado("1", ("X",), ("X",)),
                resultado("2", ("Y",), ("Z",)),
                resultado("3", ("W",), ("W",)),
                resultado("4", ("V",), ("Q",)),
            ]
        )
        self.assertAlmostEqual(a.recall, 0.5)

    def test_cobertura_media_e_a_media_das_coberturas(self):
        a = self._avaliacao(
            [
                resultado("1", ("A", "B"), ("A",)),  # 0.5
                resultado("2", ("C",), ("C",)),  # 1.0
            ]
        )
        self.assertAlmostEqual(a.cobertura_media, 0.75)

    def test_mrr_conferido_a_mao(self):
        a = self._avaliacao(
            [
                resultado("1", ("A",), ("A",)),  # 1/1
                resultado("2", ("B",), ("X", "B")),  # 1/2
                resultado("3", ("C",), ("X", "Y")),  # 0
            ]
        )
        self.assertAlmostEqual(a.mrr, (1.0 + 0.5 + 0.0) / 3)

    def test_por_tipo_separa_as_medias(self):
        """Sem isto, mediação que ajuda um tipo e atrapalha outro parece empate."""
        a = self._avaliacao(
            [
                resultado("1", ("A",), ("A",), tipo="duvida_factual"),
                resultado("2", ("B",), ("B",), tipo="duvida_factual"),
                resultado("3", ("C",), ("X",), tipo="exploracao"),
                resultado("4", ("D",), ("X",), tipo="exploracao"),
            ]
        )
        por_tipo = a.por_tipo()
        self.assertEqual(por_tipo["duvida_factual"], (2, 1.0))
        self.assertEqual(por_tipo["exploracao"], (2, 0.0))

    def test_avaliacao_vazia_nao_divide_por_zero(self):
        a = self._avaliacao([])
        self.assertEqual((a.recall, a.cobertura_media, a.mrr), (0.0, 0.0, 0.0))


class TestExecucao(unittest.TestCase):
    def test_usa_a_demanda_e_o_k_pedidos(self):
        recuperador = RecuperadorFalso(padrao=[trecho("Lore:Hist")])
        avaliar([caso("a", ("Lore:Hist",))], recuperador, k=7)
        self.assertEqual(recuperador.consultas, [("pergunta a", 7)])

    def test_paginas_repetidas_contam_uma_vez_e_pela_primeira_posicao(self):
        """Dois trechos da mesma página não são dois acertos."""
        recuperador = RecuperadorFalso(padrao=[trecho("Lore:A"), trecho("Lore:A"), trecho("Lore:B")])
        r = avaliar([caso("a", ("Lore:B",))], recuperador, k=3)
        self.assertEqual(r.resultados[0].paginas_recuperadas, ("Lore:A", "Lore:B"))
        self.assertEqual(r.resultados[0].posicao_do_primeiro_acerto, 2)

    def test_nao_gera_texto_nenhum(self):
        """Camada 1 é só recuperação: nenhum gerador é construído ou chamado."""
        recuperador = RecuperadorFalso(padrao=[trecho("Lore:A")])
        r = avaliar([caso("a", ("Lore:A",))], recuperador, k=5)
        self.assertEqual(r.total, 1)


class TestOrcamento(unittest.TestCase):
    """O que chega ao modelo, e não só o que foi recuperado."""

    def test_sem_ajuste_nao_mede_orcamento(self):
        r = avaliar([caso("a", ("Lore:A",))], RecuperadorFalso(padrao=[trecho("Lore:A")]), k=5)
        self.assertFalse(r.mediu_orcamento)
        self.assertEqual(r.recall_no_prompt, r.recall)

    def test_acerto_cortado_pelo_orcamento_nao_conta_no_prompt(self):
        recuperador = RecuperadorFalso(padrao=[trecho("Lore:A"), trecho("Lore:B"), trecho("Lore:C")])
        casos = [caso("a", ("Lore:A",)), caso("c", ("Lore:C",))]
        r = avaliar(casos, recuperador, k=3, ajustar=lambda pergunta, trechos: trechos[:2])

        self.assertEqual(r.recall, 1.0)
        self.assertEqual(r.recall_no_prompt, 0.5)
        self.assertEqual(r.casos_cortados, 2)
        self.assertEqual(r.resultados[1].paginas_no_prompt, ("Lore:A", "Lore:B"))

    def test_sem_corte_os_dois_recalls_batem(self):
        recuperador = RecuperadorFalso(padrao=[trecho("Lore:A")])
        r = avaliar([caso("a", ("Lore:A",))], recuperador, k=1, ajustar=lambda pergunta, trechos: trechos)
        self.assertTrue(r.mediu_orcamento)
        self.assertEqual(r.casos_cortados, 0)
        self.assertEqual(r.recall_no_prompt, r.recall)

    def test_trechos_por_caso_conta_trechos_e_nao_paginas(self):
        """Com recortes grandes, várias fatias da mesma página são o normal."""
        recuperador = RecuperadorFalso(padrao=[trecho("Lore:A"), trecho("Lore:A"), trecho("Lore:B")])
        r = avaliar([caso("a", ("Lore:A",))], recuperador, k=None)
        self.assertEqual(r.trechos_por_caso, 3)


class TestGabarito(unittest.TestCase):
    def test_le_o_formato_completo(self):
        arquivo = gravar(
            [
                json.dumps(
                    {
                        "id": "a1",
                        "demanda": "o que são os Hist?",
                        "tipo_de_demanda": "duvida_factual",
                        "paginas_esperadas": ["Lore:Hist"],
                        "observacao": "nota",
                    }
                )
            ]
        )
        (unico,) = carregar_casos(arquivo)
        self.assertEqual(unico.identificador, "a1")
        self.assertEqual(unico.paginas_esperadas, ("Lore:Hist",))
        self.assertEqual(unico.tipo_de_demanda, "duvida_factual")

    def test_tipo_ausente_vira_indefinido(self):
        arquivo = gravar([json.dumps({"id": "a1", "demanda": "x", "paginas_esperadas": ["P"]})])
        self.assertEqual(carregar_casos(arquivo)[0].tipo_de_demanda, "indefinido")

    def test_linha_em_branco_e_ignorada(self):
        arquivo = gravar([json.dumps({"id": "a", "demanda": "x", "paginas_esperadas": ["P"]}), "", "  "])
        self.assertEqual(len(carregar_casos(arquivo)), 1)

    def test_json_invalido_nomeia_a_linha(self):
        arquivo = gravar([json.dumps({"id": "a", "demanda": "x", "paginas_esperadas": ["P"]}), "{quebrado"])
        with self.assertRaises(ErroConfiguracao) as capturado:
            carregar_casos(arquivo)
        self.assertIn("linha 2", str(capturado.exception))

    def test_campo_faltando_nomeia_o_campo(self):
        arquivo = gravar([json.dumps({"id": "a", "demanda": "x"})])
        with self.assertRaises(ErroConfiguracao) as capturado:
            carregar_casos(arquivo)
        self.assertIn("paginas_esperadas", str(capturado.exception))

    def test_identificador_repetido_e_erro(self):
        """Sem id único, `comparar` casaria os casos errados entre rodadas."""
        linha = json.dumps({"id": "a", "demanda": "x", "paginas_esperadas": ["P"]})
        with self.assertRaises(ErroConfiguracao) as capturado:
            carregar_casos(gravar([linha, linha]))
        self.assertIn("duas vezes", str(capturado.exception))

    def test_arquivo_ausente_diz_onde_deveria_estar(self):
        with self.assertRaises(ErroConfiguracao) as capturado:
            carregar_casos(Path("/nao/existe/casos.jsonl"))
        self.assertIn("casos.jsonl", str(capturado.exception))

    def test_arquivo_vazio_e_erro(self):
        with self.assertRaises(ErroConfiguracao):
            carregar_casos(gravar([]))


class TestComparacao(unittest.TestCase):
    def _avaliacao(self, resultados) -> ResultadoDaAvaliacao:
        return ResultadoDaAvaliacao(resultados=resultados, k=5, segundos=0.0)

    def test_lista_so_o_que_mudou(self):
        antes = self._avaliacao([resultado("1", ("A",), ("A",)), resultado("2", ("B",), ("B",))])
        depois = self._avaliacao([resultado("1", ("A",), ("A",)), resultado("2", ("B",), ("X", "B"))])
        mudancas = comparar(antes, depois)
        self.assertEqual([c.identificador for c, _, _ in mudancas], ["2"])
        self.assertEqual(mudancas[0][1:], (1, 2))

    def test_o_que_piorou_vem_primeiro(self):
        """Regressão tem de ser a primeira coisa que se lê."""
        antes = self._avaliacao([resultado("melhorou", ("A",), ("X", "A")), resultado("piorou", ("B",), ("B",))])
        depois = self._avaliacao([resultado("melhorou", ("A",), ("A",)), resultado("piorou", ("B",), ("X", "Y"))])
        mudancas = comparar(antes, depois)
        self.assertEqual(mudancas[0][0].identificador, "piorou")

    def test_caso_ausente_na_outra_rodada_e_ignorado(self):
        antes = self._avaliacao([resultado("1", ("A",), ("A",))])
        depois = self._avaliacao([resultado("2", ("B",), ("B",))])
        self.assertEqual(comparar(antes, depois), [])

    def test_sem_mudanca_devolve_vazio(self):
        a = self._avaliacao([resultado("1", ("A",), ("A",))])
        self.assertEqual(comparar(a, a), [])


class TestGabaritoDoRepositorio(unittest.TestCase):
    """Impede commitar um gabarito quebrado — mesmo papel do teste dos marcos."""

    def setUp(self):
        self.casos = carregar_casos(Path(__file__).resolve().parents[1] / "avaliacao" / "casos.jsonl")

    def test_carrega_sem_erro(self):
        self.assertGreaterEqual(len(self.casos), 30)

    def test_todo_caso_tem_pagina_esperada(self):
        for caso_ in self.casos:
            self.assertTrue(caso_.paginas_esperadas, f"{caso_.identificador} não tem página esperada")

    def test_cobre_os_tres_tipos_de_demanda(self):
        """Os três tipos vêm de fase-3 §4; sem os três não dá pra ver onde a mediação ajuda."""
        tipos = {caso_.tipo_de_demanda for caso_ in self.casos}
        self.assertEqual(tipos, {"duvida_factual", "exploracao", "produto_acabado"})


if __name__ == "__main__":
    unittest.main()
