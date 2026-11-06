"""Indicadores de qualidade sem referência, nível por página e a etapa de normalização."""

import json
import tempfile
import unittest
from pathlib import Path

from rag.config import ConfigNormalizacao, ConfigQualidade
from rag.etapas import normalizacao
from rag.qualidade_ocr import indicadores_da_pagina, nivel_da_pagina, tem_colunas
from rag.texto_posicionado import Linha, PaginaPosicionada, Palavra, Regiao, escrever_page_xml

CONFIG = ConfigQualidade(minimo_de_palavras=3)
CONHECIDAS = {"a", "de", "educação", "adultos", "círculos", "cultura", "texto", "outro", "da", "página"}


def verificador(palavras, idioma):
    if idioma != "por":
        return None
    return {p for p in palavras if p.lower() not in CONHECIDAS}


def sugeridor(palavras, idioma):
    return {"circulos": ["círculos", "circulo"], "educaçao": ["educação"]}


def regiao(id_, x0, x1, y0, y1, linhas=2, tipo="texto", confianca=0.99):
    return Regiao(
        id_,
        tipo,
        ((x0, y0), (x1, y0), (x1, y1), (x0, y1)),
        tuple(Linha(f"{id_}l{i}", "texto", palavras=(Palavra("texto", confianca=confianca),)) for i in range(linhas)),
    )


class TestIndicadores(unittest.TestCase):
    def test_fracao_conta_so_as_minusculas(self):
        ind = indicadores_da_pagina("Freire e a educação de adultos xyzw", "por", CONFIG, verificador)
        # minúsculas: e, a, educação, de, adultos, xyzw → "e" e "xyzw" desconhecidas
        self.assertAlmostEqual(ind["fora_do_dicionario"], 2 / 6)
        self.assertEqual(ind["possiveis_nomes"], 1)
        self.assertIn("xyzw", ind["suspeitas"])

    def test_sem_dicionario_e_none_nunca_zero(self):
        ind = indicadores_da_pagina("texto de outro idioma", "fra", CONFIG, verificador)
        self.assertIsNone(ind["fora_do_dicionario"])
        self.assertIsNone(ind["acentos_perdidos"])

    def test_acento_perdido_detectado_sem_trocar_nada(self):
        ind = indicadores_da_pagina("a cultura de circulos", "por", CONFIG, verificador, sugeridor)
        self.assertEqual(ind["acentos_perdidos"], 1)
        self.assertEqual(ind["exemplos_de_acento"], ["circulos → círculos"])

    def test_caixa_e_palavra_curta_nao_sao_acento(self):
        sugestoes = {"aaaa": ["AAAA"], "pe": ["pé"]}
        ind = indicadores_da_pagina("a cultura aaaa pe", "por", CONFIG, verificador, lambda p, i: sugestoes)
        self.assertEqual(ind["acentos_perdidos"], 0)

    def test_colunas(self):
        lado_a_lado = PaginaPosicionada(
            1000, 1000, regioes=(regiao("a", 0, 400, 0, 800), regiao("b", 500, 900, 100, 900))
        )
        empilhadas = PaginaPosicionada(1000, 1000, regioes=(regiao("a", 0, 900, 0, 400), regiao("b", 0, 900, 500, 900)))
        titulo_ao_lado = PaginaPosicionada(
            1000, 1000, regioes=(regiao("a", 0, 400, 0, 800), regiao("b", 500, 900, 0, 50, linhas=1))
        )
        self.assertTrue(tem_colunas(lado_a_lado))
        self.assertFalse(tem_colunas(empilhadas))
        self.assertFalse(tem_colunas(titulo_ao_lado))

    def test_confianca_fora_das_regioes_ignoradas(self):
        pagina = PaginaPosicionada(
            1000,
            1000,
            regioes=(regiao("a", 0, 900, 0, 400), regiao("c", 0, 900, 900, 990, tipo="carimbo", confianca=0.1)),
        )
        ind = indicadores_da_pagina(
            "texto", "por", CONFIG, verificador, posicionada=pagina, ignorar=frozenset({"carimbo"})
        )
        self.assertAlmostEqual(ind["confianca_media"], 0.99)
        self.assertEqual(ind["fracao_hesitante"], 0.0)


class TestNivel(unittest.TestCase):
    def ind(self, fracao, palavras=100, caracteres=500, hesitante=None):
        return {
            "fora_do_dicionario": fracao,
            "palavras": palavras,
            "caracteres": caracteres,
            "fracao_hesitante": hesitante,
        }

    def test_limiares(self):
        config = ConfigQualidade()
        self.assertEqual(nivel_da_pagina(self.ind(0.02), "ocr", config), "bom")
        self.assertEqual(nivel_da_pagina(self.ind(0.05), "ocr", config), "regular")
        self.assertEqual(nivel_da_pagina(self.ind(0.20), "ocr", config), "ruim")

    def test_hesitacao_baixa_um_nivel(self):
        self.assertEqual(nivel_da_pagina(self.ind(0.02, hesitante=0.3), "ocr", ConfigQualidade()), "regular")

    def test_original_vazia_curta_e_sem_dicionario(self):
        config = ConfigQualidade()
        self.assertEqual(nivel_da_pagina(self.ind(0.5), "digital_nativo", config), "texto original")
        self.assertEqual(nivel_da_pagina(self.ind(None, palavras=0, caracteres=0), "sem_texto", config), "ruim")
        self.assertEqual(nivel_da_pagina(self.ind(0.0, palavras=5), "ocr", config), "sem medida")
        self.assertEqual(nivel_da_pagina(self.ind(None), "ocr", config), "sem medida")


class TestEtapaDeNormalizacao(unittest.TestCase):
    def setUp(self):
        self._temporario = tempfile.TemporaryDirectory()
        self.pasta = Path(self._temporario.name) / "texto"
        doc = self.pasta / "123_9"
        (doc / "a.pdf.paginas").mkdir(parents=True)
        (doc / "a.pdf.txt").write_text("a educa-\nção\fpágina digital\f", encoding="utf-8")
        registro = {"handle": "123/9", "pasta_item": "item", "arquivo": "a.pdf", "idioma": "por",
                    "origem_por_pagina": ["ocr", "digital_nativo", "sem_texto"]}  # fmt: skip
        (doc / "a.pdf.json").write_text(json.dumps(registro), encoding="utf-8")
        self.doc = doc

    def tearDown(self):
        self._temporario.cleanup()

    def executar(self):
        return normalizacao.executar(
            self.pasta,
            ConfigNormalizacao(),
            CONFIG,
            frozenset({"carimbo"}),
            lambda registro: registro["idioma"],
            verificador,
        )

    def test_mesmo_numero_de_paginas(self):
        resultado = self.executar()
        self.assertEqual(resultado.processados, 1)
        paginas = (self.doc / "a.pdf.normalizado.txt").read_text(encoding="utf-8").split("\f")
        self.assertEqual(paginas, ["a educação", "página digital", ""])
        qualidade = json.loads((self.doc / "a.pdf.qualidade.json").read_text(encoding="utf-8"))
        self.assertEqual([p["origem"] for p in qualidade["paginas"]], ["ocr", "digital_nativo", "sem_texto"])
        self.assertEqual(qualidade["paginas"][2]["nivel"], "ruim")

    def test_revisada_tem_precedencia_sobre_o_ocr(self):
        def pagina(texto):
            linha = Linha("l1", texto, contorno=((0, 0), (10, 0), (10, 10), (0, 10)))
            return escrever_page_xml(PaginaPosicionada(100, 100, regioes=(Regiao("r1", "texto", (), (linha,)),)))

        (self.doc / "a.pdf.paginas" / "pagina_0001.ocr.xml").write_text(pagina("do ocr"), encoding="utf-8")
        (self.doc / "a.pdf.paginas" / "pagina_0001.revisada.xml").write_text(pagina("revisada"), encoding="utf-8")
        self.executar()
        primeira = (self.doc / "a.pdf.normalizado.txt").read_text(encoding="utf-8").split("\f")[0]
        self.assertEqual(primeira, "revisada")


if __name__ == "__main__":
    unittest.main()


class TestPlanilha(unittest.TestCase):
    def test_quatro_abas_com_um_documento(self):
        import openpyxl

        from rag.clientes.planilha import gravar_planilha
        from rag.relatorio_ocr import montar_abas

        pagina = {"pagina": 1, "origem": "ocr", "nivel": "ruim", "caracteres": 0, "palavras": 0,
                  "fora_do_dicionario": None, "acentos_perdidos": None, "linhas_hesitantes": None,
                  "confianca_media": None, "fracao_hesitante": None, "regras": {}}  # fmt: skip
        qualidade = {"handle": "123/9", "arquivo": "a.pdf", "idioma": "por", "paginas": [pagina],
                     "linhas_por_tipo": {"carimbo": 5}, "ocr_ferramenta": "kraken"}  # fmt: skip
        abas, resumos = montar_abas({("123/9", "a.pdf"): qualidade}, {"123/9": "Título"}, ConfigQualidade(), "hoje")
        self.assertIn("P1 · 1 página(s) sem texto: 1", resumos[0]["problemas"])
        self.assertIn("P8 · tirados do texto: 5 linha(s) de carimbo", resumos[0]["problemas"])
        with tempfile.TemporaryDirectory() as pasta:
            destino = gravar_planilha(Path(pasta) / "r.xlsx", abas)
            livro = openpyxl.load_workbook(destino)
            self.assertEqual(livro.sheetnames, ["Resumo", "Documentos", "Páginas", "Legenda"])
            self.assertEqual(livro["Documentos"]["B2"].value, "Título")
            self.assertEqual(livro["Documentos"]["J2"].value, "ruim")
