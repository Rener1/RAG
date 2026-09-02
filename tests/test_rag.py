"""Testes da recuperação, da montagem de prompt e do ciclo completo."""

import unittest

from apoio import EmbutidorFalso, GeradorFalso, ReordenadorFalso, RepositorioFalso

from rag.config import ConfigBusca
from rag.etapas.geracao import formatar_trechos, montar_prompt
from rag.etapas.recuperacao import Recuperador, recortar_por_limiar_relativo
from rag.modelos import Chunk, TrechoRecuperado
from rag.orquestrador import MotorRag
from rag.protocolos import Reordenador


def montar_recuperador(quantidade=3, **ajustes):
    """Recuperador com quantidade fixa.

    `limiar_relativo=0` é explícito porque o padrão do projeto liga a quantidade
    dinâmica, e nestes testes o que se verifica é justamente o `k` fixo valer.
    """
    repositorio = RepositorioFalso()
    for i in range(quantidade):
        repositorio.pontos[f"doc.txt::{i}"] = Chunk(f"doc.txt::{i}", f"trecho {i}", "doc.txt", f"Título {i}", i)
    return Recuperador(EmbutidorFalso(), repositorio, ConfigBusca(k=2, limiar_relativo=0.0, **ajustes))


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
        motor = MotorRag(
            Recuperador(EmbutidorFalso(), RepositorioFalso(), ConfigBusca(limiar_relativo=0.0)), self.gerador
        )
        resposta = motor.responder("pergunta")
        self.assertEqual(resposta.texto, "")
        self.assertEqual(self.gerador.ultimo_prompt, "")

    def test_montador_de_prompt_e_substituivel(self):
        """O marco pedagógico entra por aqui, sem alterar o motor."""
        motor = MotorRag(montar_recuperador(), self.gerador, lambda p, t: f"PROMPT CUSTOMIZADO: {p}")
        motor.responder("pergunta")
        self.assertEqual(self.gerador.ultimo_prompt, "PROMPT CUSTOMIZADO: pergunta")


class TestLimiarRelativo(unittest.TestCase):
    """Quantidade de trechos conforme a pergunta, e não fixa.

    Relativo ao topo de cada pergunta porque o score absoluto não serve: medido
    neste corpus, trecho relevante e irrelevante têm a mesma faixa de score
    (medianas 0,552 e 0,551), e corte fixo deixa perguntas legítimas sem
    resultado nenhum.
    """

    def _trechos(self, *scores):
        return [
            TrechoRecuperado(
                texto=f"t{n}", titulo_pagina=f"P{n}", documento_origem=f"{n}.txt", chunk_id=str(n), score=s
            )
            for n, s in enumerate(scores)
        ]

    def test_queda_abrupta_devolve_poucos(self):
        trechos = self._trechos(0.90, 0.88, 0.50, 0.48, 0.40, 0.30)
        self.assertEqual(len(recortar_por_limiar_relativo(trechos, 0.90, minimo=2)), 2)

    def test_plato_devolve_muitos(self):
        trechos = self._trechos(0.90, 0.89, 0.88, 0.87, 0.86, 0.85)
        self.assertEqual(len(recortar_por_limiar_relativo(trechos, 0.90, minimo=2)), 6)

    def test_o_piso_impede_devolver_quase_nada(self):
        """Uma fonte só é pouco para fundamentar qualquer coisa."""
        trechos = self._trechos(0.90, 0.10, 0.09, 0.08)
        self.assertEqual(len(recortar_por_limiar_relativo(trechos, 0.90, minimo=3)), 3)

    def test_limiar_zero_desliga(self):
        trechos = self._trechos(0.90, 0.10)
        self.assertEqual(len(recortar_por_limiar_relativo(trechos, 0.0, minimo=1)), 2)

    def test_lista_vazia_nao_estoura(self):
        self.assertEqual(recortar_por_limiar_relativo([], 0.90, minimo=5), [])

    def test_o_corte_e_relativo_e_nao_absoluto(self):
        """Duas perguntas com escalas de score diferentes devolvem o mesmo tanto."""
        altos = self._trechos(0.90, 0.87, 0.50)
        baixos = self._trechos(0.50, 0.485, 0.28)
        self.assertEqual(
            len(recortar_por_limiar_relativo(altos, 0.95, minimo=1)),
            len(recortar_por_limiar_relativo(baixos, 0.95, minimo=1)),
        )

    def test_o_padrao_do_projeto_usa_quantidade_dinamica(self):
        """Se este teste quebrar, o padrão mudou — confira a medição antes de aceitar."""
        self.assertGreater(ConfigBusca().limiar_relativo, 0.0)

    def test_k_explicito_ignora_a_politica_dinamica(self):
        """A varredura de k do harness precisa que `--k N` signifique N."""
        config = ConfigBusca(k=3, limiar_relativo=0.9, k_maximo=20)
        repositorio = RepositorioFalso()
        for n in range(10):
            repositorio.pontos[str(n)] = Chunk(
                chunk_id=str(n), texto=f"t{n}", documento_origem="d.txt", titulo_pagina="P", chunk_index=n
            )
        recuperador = Recuperador(EmbutidorFalso(), repositorio, config)
        self.assertEqual(len(recuperador.buscar("pergunta", k=7)), 7)


class TestReordenacao(unittest.TestCase):
    """Fiação do cross-encoder na recuperação, sem carregar modelo.

    A busca vetorial compara dois vetores calculados em separado; o
    cross-encoder lê pergunta e trecho juntos e julga melhor. Como não dá para
    pré-calcular, ele só reordena um punhado de candidatos — daí o desenho de
    dois estágios, e daí a importância de o pool ser grande.
    """

    def _montar(self, reordenador=None, **ajustes):
        repositorio = RepositorioFalso()
        for i, titulo in enumerate(["Ruim", "Meio", "Bom", "Ótimo"]):
            repositorio.pontos[f"d::{i}"] = Chunk(f"d::{i}", f"trecho {i}", "d.txt", f"Lore:{titulo}", i)
        config = ConfigBusca(k=2, limiar_relativo=0.0, **ajustes)
        return Recuperador(EmbutidorFalso(), repositorio, config, reordenador=reordenador)

    def test_a_ordem_do_reordenador_vale(self):
        reordenador = ReordenadorFalso(preferencia=["Lore:Ótimo", "Lore:Bom"])
        trechos = self._montar(reordenador, reordenar=True).buscar("pergunta")
        self.assertEqual([t.titulo_pagina for t in trechos], ["Lore:Ótimo", "Lore:Bom"])

    def test_desligado_nao_chama_o_modelo(self):
        reordenador = ReordenadorFalso(preferencia=["Lore:Ótimo"])
        self._montar(reordenador, reordenar=False).buscar("pergunta")
        self.assertEqual(reordenador.chamadas, [])

    def test_o_pool_e_maior_que_o_k_entregue(self):
        """Um cross-encoder só melhora o que recebe: 20 candidatos medem pior que 50."""
        reordenador = ReordenadorFalso()
        self._montar(reordenador, reordenar=True, candidatos_para_reordenar=50).buscar("pergunta")
        self.assertEqual(reordenador.chamadas[0][1], 4, "deveria reordenar tudo o que o repositório tinha")

    def test_falha_do_modelo_devolve_a_ordem_vetorial(self):
        """A recuperação não pode cair porque um modelo opcional tropeçou."""
        reordenador = ReordenadorFalso(erro=RuntimeError("modelo estourou"))
        trechos = self._montar(reordenador, reordenar=True).buscar("pergunta")
        self.assertEqual(len(trechos), 2)

    def test_sem_reordenador_o_caminho_e_o_de_sempre(self):
        self.assertEqual(len(self._montar(None, reordenar=True).buscar("pergunta")), 2)

    def test_cumpre_o_protocolo(self):
        self.assertIsInstance(ReordenadorFalso(), Reordenador)


if __name__ == "__main__":
    unittest.main()
