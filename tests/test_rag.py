"""Testes da recuperação, da montagem de prompt e do ciclo completo."""

import unittest

from apoio import EmbutidorFalso, GeradorFalso, RepositorioFalso

from rag.config import ConfigBusca
from rag.etapas.geracao import formatar_trechos, montar_prompt
from rag.etapas.recuperacao import Recuperador
from rag.modelos import Chunk, TrechoRecuperado
from rag.orquestrador import MotorRag


def montar_recuperador(quantidade=3):
    repositorio = RepositorioFalso()
    for i in range(quantidade):
        repositorio.pontos[f"doc.txt::{i}"] = Chunk(f"doc.txt::{i}", f"trecho {i}", "doc.txt", f"Título {i}", i)
    return Recuperador(EmbutidorFalso(), repositorio, ConfigBusca(k=2))


class TestRecuperacao(unittest.TestCase):
    def test_respeita_o_k_configurado(self):
        self.assertEqual(len(montar_recuperador(5).buscar("pergunta")), 2)

    def test_k_do_argumento_sobrepoe_o_configurado(self):
        self.assertEqual(len(montar_recuperador(5).buscar("pergunta", k=4)), 4)

    def test_devolve_trechos_com_proveniencia(self):
        trecho = montar_recuperador().buscar("pergunta")[0]
        self.assertIsInstance(trecho, TrechoRecuperado)
        self.assertTrue(trecho.titulo_pagina)
        self.assertTrue(trecho.chunk_id)


class TestPrompt(unittest.TestCase):
    def setUp(self):
        self.trechos = [
            TrechoRecuperado("Texto um.", "Lore:A", "a.txt", "a.txt::0", 0.9),
            TrechoRecuperado("Texto dois.", "Lore:B", "b.txt", "b.txt::0", 0.8),
        ]

    def test_trechos_saem_etiquetados_pela_fonte(self):
        formatado = formatar_trechos(self.trechos)
        self.assertIn("[Fonte 1: Lore:A]", formatado)
        self.assertIn("[Fonte 2: Lore:B]", formatado)

    def test_prompt_carrega_pergunta_e_trechos(self):
        prompt = montar_prompt("Quem é A?", self.trechos)
        self.assertIn("Quem é A?", prompt)
        self.assertIn("Texto um.", prompt)
        self.assertIn("Lore:A", prompt)

    def test_prompt_instrui_a_nao_inventar(self):
        """Sem essa instrução, o modelo responde de memória em vez do corpus."""
        prompt = montar_prompt("p", self.trechos)
        self.assertIn("SOMENTE com base nos trechos", prompt)


class TestMotorRag(unittest.TestCase):
    def setUp(self):
        self.gerador = GeradorFalso()
        self.motor = MotorRag(montar_recuperador(), self.gerador)

    def test_ciclo_completo_devolve_resposta_com_fontes(self):
        resposta = self.motor.responder("pergunta")
        self.assertEqual(resposta.texto, "resposta gerada")
        self.assertEqual(len(resposta.trechos), 2)
        self.assertGreaterEqual(resposta.segundos, 0)

    def test_o_prompt_enviado_contem_os_trechos_recuperados(self):
        self.motor.responder("pergunta")
        self.assertIn("trecho 0", self.gerador.ultimo_prompt)

    def test_sem_trechos_nao_chama_o_gerador(self):
        """Gerar sem material recuperado é convidar o modelo a inventar."""
        motor = MotorRag(Recuperador(EmbutidorFalso(), RepositorioFalso(), ConfigBusca()), self.gerador)
        resposta = motor.responder("pergunta")
        self.assertEqual(resposta.texto, "")
        self.assertEqual(self.gerador.ultimo_prompt, "")

    def test_montador_de_prompt_e_substituivel(self):
        """O marco pedagógico entra por aqui, sem alterar o motor."""
        motor = MotorRag(montar_recuperador(), self.gerador, lambda p, t: f"PROMPT CUSTOMIZADO: {p}")
        motor.responder("pergunta")
        self.assertEqual(self.gerador.ultimo_prompt, "PROMPT CUSTOMIZADO: pergunta")


if __name__ == "__main__":
    unittest.main()
