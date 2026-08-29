"""Testes das funções puras do download — limpeza de wikitexto e nome de arquivo."""

import tempfile
import unittest
from pathlib import Path

from apoio import ColetorFalso

from rag.config import ConfigDownload
from rag.etapas import download


class TestNomeDeArquivo(unittest.TestCase):
    def test_troca_caractere_invalido_por_underscore(self):
        self.assertEqual(download.nome_arquivo_seguro("Lore:Abah's Landing"), "Lore_Abah_s_Landing.txt")

    def test_nao_deixa_underscore_nas_pontas(self):
        nome = download.nome_arquivo_seguro(":::Título:::")
        self.assertFalse(nome.startswith("_"))
        self.assertEqual(nome, "Título.txt")

    def test_e_estavel_entre_chamadas(self):
        """O nome compõe o chunk_id, que é a chave do índice: não pode variar."""
        titulo = "Lore:2920, The Last Year"
        self.assertEqual(download.nome_arquivo_seguro(titulo), download.nome_arquivo_seguro(titulo))


class TestLimpezaDeWikitexto(unittest.TestCase):
    def test_redirect_vira_vazio(self):
        self.assertEqual(download.limpar_wikitexto("#REDIRECT [[Lore:Outra]]"), "")

    def test_redirect_em_caixa_baixa_tambem(self):
        self.assertEqual(download.limpar_wikitexto("#redirect [[Lore:Outra]]"), "")

    def test_remove_bloco_de_referencia(self):
        """Sem isso, o texto da citação entra no meio do parágrafo e vira ruído."""
        limpo = download.limpar_wikitexto("Afirmação<ref>Fonte da citação</ref> segue.")
        self.assertNotIn("Fonte da citação", limpo)
        self.assertIn("Afirmação", limpo)

    def test_remove_referencia_de_tag_fechada(self):
        limpo = download.limpar_wikitexto("Texto<ref name='x'/> continua.")
        self.assertNotIn("<ref", limpo)

    def test_desmonta_marcacao_de_link_e_negrito(self):
        limpo = download.limpar_wikitexto("'''Negrito''' e [[Lore:X|link]].")
        self.assertIn("Negrito", limpo)
        self.assertIn("link", limpo)
        self.assertNotIn("[[", limpo)


class TestEtapaDeDownload(unittest.TestCase):
    """A etapa inteira, com o coletor injetado — sem rede."""

    def setUp(self):
        self.config = ConfigDownload(titulos_por_lote=2, lotes_paralelos=2, tamanho_minimo=10)
        self.paginas = {
            "Lore:Um": "Conteúdo suficientemente longo para passar do mínimo.",
            "Lore:Dois": "Outro conteúdo bem longo, também acima do mínimo.",
            "Lore:Curto": "x",
            "Lore:Redirect": "#REDIRECT [[Lore:Um]]",
        }

    def test_grava_um_arquivo_por_pagina_com_cabecalho(self):
        with tempfile.TemporaryDirectory() as pasta:
            destino = Path(pasta)
            resultado = download.executar(self.config, destino, ColetorFalso(self.paginas))

            self.assertEqual(resultado.processados, 2)
            conteudo = (destino / "Lore_Um.txt").read_text(encoding="utf-8")
            self.assertTrue(conteudo.startswith("# Lore:Um\n\n"))

    def test_descarta_pagina_curta_e_redirect(self):
        with tempfile.TemporaryDirectory() as pasta:
            destino = Path(pasta)
            resultado = download.executar(self.config, destino, ColetorFalso(self.paginas))

            self.assertEqual(resultado.ignorados, 2)
            self.assertFalse((destino / "Lore_Curto.txt").exists())
            self.assertFalse((destino / "Lore_Redirect.txt").exists())

    def test_repetir_nao_rebaixa_o_que_ja_esta_em_disco(self):
        """É o que torna barato retomar um download interrompido."""
        with tempfile.TemporaryDirectory() as pasta:
            destino = Path(pasta)
            download.executar(self.config, destino, ColetorFalso(self.paginas))

            segundo = ColetorFalso(self.paginas)
            resultado = download.executar(self.config, destino, segundo)

            self.assertEqual(resultado.processados, 0)
            pedidos = [titulo for lote in segundo.lotes_pedidos for titulo in lote]
            self.assertNotIn("Lore:Um", pedidos)

    def test_lote_que_falha_e_relatado_sem_derrubar_a_etapa(self):
        class ColetorQuebrado(ColetorFalso):
            def baixar_lote(self, titulos):
                raise RuntimeError("rede caiu")

        with tempfile.TemporaryDirectory() as pasta:
            resultado = download.executar(self.config, Path(pasta), ColetorQuebrado(self.paginas))
            self.assertTrue(resultado.houve_falha)
            self.assertEqual(resultado.processados, 0)


if __name__ == "__main__":
    unittest.main()
