"""Testes do corte em chunks — a etapa com mais regra de negócio pura."""

import unittest

from apoio import *  # noqa: F401,F403  (ajusta o sys.path)

from rag.config import ConfigChunking
from rag.etapas import chunking


class TestExtracaoDeTitulo(unittest.TestCase):
    def test_extrai_titulo_e_corpo_do_formato_gravado_pelo_download(self):
        titulo, corpo = chunking.extrair_titulo_e_corpo("# Lore:Argonian\n\nTexto do artigo.")
        self.assertEqual(titulo, "Lore:Argonian")
        self.assertEqual(corpo, "Texto do artigo.")

    def test_arquivo_sem_cabecalho_nao_quebra(self):
        titulo, corpo = chunking.extrair_titulo_e_corpo("Só o corpo, sem título.")
        self.assertEqual(titulo, "desconhecido")


class TestDivisaoDeParagrafoGigante(unittest.TestCase):
    """O teto de tamanho precisa valer sempre, não 'na maioria dos casos'."""

    def test_corta_por_frase_quando_ha_pontuacao(self):
        texto = ("Uma frase de tamanho razoável. " * 20).strip()
        pedacos = chunking.dividir_paragrafo_gigante(texto, 100)
        self.assertTrue(all(len(p) <= 100 for p in pedacos))

    def test_cai_para_corte_por_palavra_sem_pontuacao(self):
        texto = " ".join(["palavra"] * 200)
        pedacos = chunking.dividir_paragrafo_gigante(texto, 50)
        self.assertTrue(all(len(p) <= 50 for p in pedacos))

    def test_corta_por_caractere_quando_nao_ha_nem_espaco(self):
        pedacos = chunking.dividir_paragrafo_gigante("x" * 500, 100)
        self.assertEqual(len(pedacos), 5)
        self.assertTrue(all(len(p) <= 100 for p in pedacos))

    def test_nao_perde_conteudo_ao_dividir(self):
        texto = " ".join(f"palavra{i}" for i in range(300))
        pedacos = chunking.dividir_paragrafo_gigante(texto, 80)
        self.assertEqual(" ".join(pedacos).split(), texto.split())


class TestEstrategiaPorParagrafo(unittest.TestCase):
    def setUp(self):
        self.config = ConfigChunking(tamanho_minimo=20, tamanho_maximo=200)

    def test_um_chunk_por_paragrafo(self):
        corpo = f"{'a' * 50}\n\n{'b' * 50}\n\n{'c' * 50}"
        self.assertEqual(len(chunking.cortar_por_paragrafo(corpo, self.config).textos), 3)

    def test_descarta_paragrafo_abaixo_do_minimo(self):
        corpo = f"curto\n\n{'a' * 50}"
        textos = chunking.cortar_por_paragrafo(corpo, self.config).textos
        self.assertEqual(len(textos), 1)

    def test_sinaliza_paragrafo_acima_do_teto(self):
        corte = chunking.cortar_por_paragrafo("x" * 500, self.config)
        self.assertTrue(corte.teve_paragrafo_gigante)
        self.assertTrue(all(len(t) <= 200 for t in corte.textos))

    def test_respeita_o_teto_em_todos_os_chunks(self):
        corpo = "\n\n".join(["y" * 900, "z" * 30, "w" * 400])
        for texto in chunking.cortar_por_paragrafo(corpo, self.config).textos:
            self.assertLessEqual(len(texto), self.config.tamanho_maximo)


class TestEstrategiaAgrupada(unittest.TestCase):
    """A variante existe justamente para não descartar parágrafo curto."""

    def setUp(self):
        self.config = ConfigChunking(estrategia="paragrafo_agrupado", tamanho_minimo=20, tamanho_maximo=200)

    def test_agrupa_paragrafos_curtos_em_vez_de_descartar(self):
        corpo = "\n\n".join(["curto um", "curto dois", "curto três"])
        textos = chunking.cortar_por_paragrafo_agrupado(corpo, self.config).textos
        self.assertEqual(len(textos), 1)
        for original in ("curto um", "curto dois", "curto três"):
            self.assertIn(original, textos[0])

    def test_padrao_descartaria_os_mesmos_paragrafos(self):
        corpo = "\n\n".join(["curto um", "curto dois", "curto três"])
        self.assertEqual(chunking.cortar_por_paragrafo(corpo, self.config).textos, [])


class TestEtapaCompleta(unittest.TestCase):
    def test_gera_jsonl_com_proveniencia_e_indice_sequencial(self):
        import json
        import tempfile
        from pathlib import Path

        from rag.modelos import ResultadoEtapa  # noqa: F401

        with tempfile.TemporaryDirectory() as pasta:
            corpus = Path(pasta) / "corpus"
            corpus.mkdir()
            (corpus / "Doc_A.txt").write_text(f"# Lore:A\n\n{'a' * 80}\n\n{'b' * 80}", encoding="utf-8")
            saida = Path(pasta) / "chunks.jsonl"

            resultado = chunking.executar(ConfigChunking(), corpus, saida)

            self.assertEqual(resultado.processados, 2)
            linhas = [json.loads(linha) for linha in saida.read_text(encoding="utf-8").splitlines()]
            self.assertEqual([linha["chunk_index"] for linha in linhas], [0, 1])
            self.assertEqual(linhas[0]["chunk_id"], "Doc_A.txt::0")
            self.assertEqual(linhas[0]["titulo_pagina"], "Lore:A")
            self.assertEqual(linhas[0]["documento_origem"], "Doc_A.txt")

    def test_nao_destroi_arquivo_anterior_se_falhar_no_meio(self):
        """A escrita é atômica: erro no meio preserva o chunks.jsonl que já existia."""
        import tempfile
        from pathlib import Path
        from unittest import mock

        with tempfile.TemporaryDirectory() as pasta:
            corpus = Path(pasta) / "corpus"
            corpus.mkdir()
            (corpus / "Doc.txt").write_text(f"# T\n\n{'a' * 80}", encoding="utf-8")
            saida = Path(pasta) / "chunks.jsonl"
            saida.write_text("conteúdo anterior\n", encoding="utf-8")

            with mock.patch.object(chunking, "percorrer_corpus", side_effect=RuntimeError("falha no meio")):
                with self.assertRaises(RuntimeError):
                    chunking.executar(ConfigChunking(), corpus, saida)

            self.assertEqual(saida.read_text(encoding="utf-8"), "conteúdo anterior\n")


if __name__ == "__main__":
    unittest.main()
