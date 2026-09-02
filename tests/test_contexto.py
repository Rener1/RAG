"""
Orçamento de janela de contexto.

O modo de falha que estes testes existem para impedir é silencioso dos dois
lados: um prompt maior que a janela é truncado pelo Ollama sem erro nenhum, e o
que se perde são os últimos trechos — justamente os que o modelo deveria citar.
Antes deste orçamento, `k` era um botão cego.

A regra central é `caber_no_orcamento` descartar trecho inteiro e nunca cortar
um pela metade: fonte citada pela metade quebra a citação verificável que o
marco exige.
"""

import re
import unittest

from apoio import GeradorFalso, MarcoFalso, RecuperadorFalso

from rag.etapas.geracao import (  # noqa: E402
    caber_no_orcamento,
    estimar_tokens,
    formatar_trechos,
    montador_do_marco,
    montar_prompt,
    ordenar_para_o_prompt,
    validar_citacoes,
)
from rag.modelos import TrechoRecuperado  # noqa: E402
from rag.orquestrador import MotorRag  # noqa: E402


def trecho(identificador: str, chars: int = 400) -> TrechoRecuperado:
    return TrechoRecuperado(
        texto="x" * chars,
        titulo_pagina=f"Lore:{identificador}",
        documento_origem=f"{identificador}.txt",
        chunk_id=identificador,
        score=0.9,
    )


class TestEstimativa(unittest.TestCase):
    def test_proporcional_ao_tamanho(self):
        self.assertEqual(estimar_tokens("x" * 4000), 1000)

    def test_arredonda_para_cima(self):
        """Subestimar o custo é o erro caro: estoura a janela em silêncio."""
        self.assertEqual(estimar_tokens("x"), 1)
        self.assertEqual(estimar_tokens("x" * 5), 2)

    def test_texto_vazio_nao_custa(self):
        self.assertEqual(estimar_tokens(""), 0)


class TestOrcamento(unittest.TestCase):
    def test_orcamento_generoso_nao_descarta(self):
        trechos = [trecho(str(n)) for n in range(5)]
        self.assertEqual(len(caber_no_orcamento(trechos, 100_000)), 5)

    def test_orcamento_zero_desliga_o_corte(self):
        trechos = [trecho(str(n)) for n in range(5)]
        self.assertEqual(len(caber_no_orcamento(trechos, 0)), 5)

    def test_descarta_do_fim_preservando_a_ordem(self):
        """A lista vem ordenada por relevância: quem sai é o menos relevante."""
        trechos = [trecho("a"), trecho("b"), trecho("c"), trecho("d")]
        # ~105 tokens por trecho de 400 chars; 250 comporta dois.
        cabem = caber_no_orcamento(trechos, 250)
        self.assertEqual([t.chunk_id for t in cabem], ["a", "b"])

    def test_overhead_reduz_o_espaco_disponivel(self):
        trechos = [trecho("a"), trecho("b"), trecho("c")]
        sem_overhead = caber_no_orcamento(trechos, 400, 0)
        com_overhead = caber_no_orcamento(trechos, 400, 300)
        self.assertGreater(len(sem_overhead), len(com_overhead))

    def test_o_primeiro_trecho_entra_mesmo_estourando(self):
        """Lista vazia faria o motor dizer 'não há material', que é pior."""
        cabem = caber_no_orcamento([trecho("gigante", chars=40_000)], 10)
        self.assertEqual(len(cabem), 1)

    def test_nunca_corta_um_trecho_no_meio(self):
        """Fonte pela metade quebra a citação verificável — sai inteira ou fica."""
        trechos = [trecho("a"), trecho("b"), trecho("c")]
        for t in caber_no_orcamento(trechos, 250):
            self.assertEqual(len(t.texto), 400)

    def test_sem_trechos_devolve_vazio(self):
        self.assertEqual(caber_no_orcamento([], 1000), [])


class TestMotorComOrcamento(unittest.TestCase):
    def _motor(self, orcamento, ao_ajustar=None, marco=None):
        trechos = [trecho(c) for c in "abcdefgh"]
        gerador = GeradorFalso()
        motor = MotorRag(
            RecuperadorFalso(padrao=trechos),
            gerador,
            montador_do_marco(marco) if marco else montar_prompt,
            orcamento_em_tokens=orcamento,
            ao_ajustar_contexto=ao_ajustar or (lambda recuperados, usados: None),
        )
        return motor, gerador

    def test_o_prompt_recebe_so_o_que_coube(self):
        motor, gerador = self._motor(orcamento=300)
        trechos, fluxo = motor.responder_em_fluxo("pergunta")
        "".join(fluxo)

        self.assertLess(len(trechos), 8)
        self.assertEqual(gerador.ultimo_prompt.count("[Fonte "), len(trechos))

    def test_a_lista_devolvida_e_a_que_foi_ao_modelo(self):
        """Exibir 8 fontes e mandar 2 faria validar_citacoes aprovar o que o modelo não viu."""
        motor, gerador = self._motor(orcamento=300)
        trechos, fluxo = motor.responder_em_fluxo("pergunta")
        "".join(fluxo)

        # Uma citação além do que sobrou tem de ser reprovada.
        self.assertEqual(validar_citacoes(f"[Fonte {len(trechos) + 1}]", trechos), [f"Fonte {len(trechos) + 1}"])
        self.assertIn(f"[Fonte {len(trechos)}:", gerador.ultimo_prompt)

    def test_avisa_a_interface_quando_descarta(self):
        vistos = []
        motor, _ = self._motor(orcamento=300, ao_ajustar=lambda r, u: vistos.append((r, u)))
        trechos, fluxo = motor.responder_em_fluxo("pergunta")
        "".join(fluxo)

        self.assertEqual(len(vistos), 1)
        self.assertEqual(vistos[0], (8, len(trechos)))

    def test_nao_avisa_quando_tudo_coube(self):
        vistos = []
        motor, _ = self._motor(orcamento=100_000, ao_ajustar=lambda r, u: vistos.append((r, u)))
        _, fluxo = motor.responder_em_fluxo("pergunta")
        "".join(fluxo)

        self.assertEqual(vistos, [])

    def test_marco_longo_encolhe_o_espaco_de_trechos(self):
        """O overhead sai do próprio montador, então marco grande cabe menos trecho."""
        curto, _ = self._motor(orcamento=600, marco=MarcoFalso({"Papel": "curto"}))
        longo, _ = self._motor(orcamento=600, marco=MarcoFalso({"Papel": "p" * 6000}))

        com_marco_curto, f1 = curto.responder_em_fluxo("pergunta")
        "".join(f1)
        com_marco_longo, f2 = longo.responder_em_fluxo("pergunta")
        "".join(f2)

        self.assertGreater(len(com_marco_curto), len(com_marco_longo))

    def test_sem_orcamento_o_comportamento_e_o_de_antes(self):
        motor, gerador = self._motor(orcamento=0)
        trechos, fluxo = motor.responder_em_fluxo("pergunta")
        "".join(fluxo)

        self.assertEqual(len(trechos), 8)


class TestRenumeracao(unittest.TestCase):
    def test_as_fontes_sao_renumeradas_apos_o_corte(self):
        """Cortar não pode deixar buraco na numeração que o modelo vai citar."""
        trechos = [trecho("a"), trecho("b"), trecho("c"), trecho("d")]
        cabem = caber_no_orcamento(trechos, 250)
        texto = formatar_trechos(cabem)

        for numero in range(1, len(cabem) + 1):
            self.assertIn(f"[Fonte {numero}:", texto)
        self.assertNotIn(f"[Fonte {len(cabem) + 1}:", texto)


class TestOrdemNoPrompt(unittest.TestCase):
    """Melhores nas pontas, medianos no meio — contra o *lost in the middle*.

    A atenção do modelo sobre contexto longo tem forma de U. Entregar em ordem
    decrescente deixava o trecho menos relevante na posição final, que é uma das
    duas que o modelo mais usa.
    """

    def _trechos(self, quantos):
        return [trecho(str(n)) for n in range(1, quantos + 1)]

    def test_o_melhor_abre_e_o_segundo_fecha(self):
        ordenados = ordenar_para_o_prompt(self._trechos(6))
        self.assertEqual(ordenados[0].chunk_id, "1")
        self.assertEqual(ordenados[-1].chunk_id, "2")

    def test_os_medianos_ficam_no_miolo(self):
        ordenados = ordenar_para_o_prompt(self._trechos(6))
        self.assertEqual([t.chunk_id for t in ordenados], ["1", "3", "5", "6", "4", "2"])

    def test_nao_perde_nem_duplica_trecho(self):
        for quantos in (0, 1, 2, 3, 7, 20):
            ordenados = ordenar_para_o_prompt(self._trechos(quantos))
            self.assertEqual(sorted(t.chunk_id for t in ordenados), sorted(t.chunk_id for t in self._trechos(quantos)))

    def test_um_trecho_so_nao_muda(self):
        self.assertEqual([t.chunk_id for t in ordenar_para_o_prompt(self._trechos(1))], ["1"])

    def test_a_numeracao_segue_a_relevancia_e_nao_a_posicao(self):
        """`[Fonte 2]` tem de ser o 2º mais relevante — é o que a tela mostra."""
        texto = formatar_trechos(self._trechos(4))
        posicoes = re.findall(r"\[Fonte (\d+): Lore:(\d+)\]", texto)
        for numero, identificador in posicoes:
            self.assertEqual(numero, identificador, "o número da fonte deixou de ser a posição na relevância")

    def test_a_citacao_continua_validavel(self):
        trechos = self._trechos(4)
        self.assertEqual(validar_citacoes("[Fonte 4]", trechos), [])
        self.assertEqual(validar_citacoes("[Fonte 5]", trechos), ["Fonte 5"])


if __name__ == "__main__":
    unittest.main()
