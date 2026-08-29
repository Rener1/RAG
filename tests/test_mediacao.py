"""
A camada de mediação entre a pergunta e o embedding.

Dois pontos concentram o risco. O primeiro é o fallback: a mediação usa o modelo
de geração, e a recuperação precisa continuar avaliável sozinha mesmo com esse
modelo fora do ar — por isso nenhum tropeço aqui pode virar exceção. O segundo é
a fusão: RRF é curto o bastante para parecer óbvio e errado o bastante para
passar despercebido, então há um caso com a conta feita à mão.
"""

import unittest

from apoio import GeradorFalso, GeradorRoteirizado, RecuperadorFalso  # noqa: F401

from rag.config import ConfigBusca, ConfigIntermediacao  # noqa: E402
from rag.erros import ErroConexao  # noqa: E402
from rag.mediacao import (  # noqa: E402
    ConsultaDecomposta,
    IntermediadorDeConsulta,
    extrair_subconsultas,
    fundir_por_rrf,
    limitar_por_documento,
)
from rag.modelos import TrechoRecuperado  # noqa: E402
from rag.orquestrador import MotorRag  # noqa: E402
from rag.protocolos import RecuperadorDeTrechos  # noqa: E402

PERGUNTA = "quem são os argonianos e qual a relação deles com os hist?"


def trecho(identificador: str, score: float = 0.9, documento: str = "") -> TrechoRecuperado:
    return TrechoRecuperado(
        texto=f"texto {identificador}",
        titulo_pagina=identificador,
        documento_origem=documento or f"{identificador}.txt",
        chunk_id=identificador,
        score=score,
    )


def montar(gerador, recuperador, **ajustes) -> IntermediadorDeConsulta:
    config = ConfigIntermediacao(**ajustes)
    return IntermediadorDeConsulta(recuperador, gerador, config, ConfigBusca(k=3))


class TestExtracao(unittest.TestCase):
    def test_lista_numerada(self):
        saida = "1. quem são os argonianos\n2. o que são os hist\n3. relação entre eles"
        self.assertEqual(len(extrair_subconsultas(saida, 3, PERGUNTA)), 3)

    def test_lista_com_traco_e_com_ponto(self):
        saida = "- quem são os argonianos\n• o que são os hist"
        self.assertEqual(extrair_subconsultas(saida, 3, PERGUNTA), ["quem são os argonianos", "o que são os hist"])

    def test_linha_que_repete_a_pergunta_e_descartada(self):
        saida = f"{PERGUNTA}\no que são os hist"
        self.assertEqual(extrair_subconsultas(saida, 3, PERGUNTA), ["o que são os hist"])

    def test_eco_do_prompt_e_descartado(self):
        saida = "Claro, aqui estão as sub-consultas:\nquem são os argonianos"
        self.assertEqual(extrair_subconsultas(saida, 3, PERGUNTA), ["quem são os argonianos"])

    def test_linha_curta_ou_longa_demais_e_descartada(self):
        saida = "ok\n" + ("x" * 300) + "\numa consulta de tamanho razoável"
        self.assertEqual(extrair_subconsultas(saida, 3, PERGUNTA), ["uma consulta de tamanho razoável"])

    def test_repetidas_ignorando_caixa_contam_uma_vez(self):
        saida = "Quem São Os Argonianos\nquem são os argonianos"
        self.assertEqual(len(extrair_subconsultas(saida, 3, PERGUNTA)), 1)

    def test_respeita_o_maximo_mesmo_com_o_modelo_falante(self):
        saida = "\n".join(f"consulta número {n} sobre o assunto" for n in range(10))
        self.assertEqual(len(extrair_subconsultas(saida, 3, PERGUNTA)), 3)

    def test_lixo_devolve_vazio(self):
        self.assertEqual(extrair_subconsultas("...\n\n?\n", 3, PERGUNTA), [])


class TestFusao(unittest.TestCase):
    def test_presente_em_mais_rankings_sobe(self):
        """b é 2º em ambos; a é 1º num só. 2/62 > 1/61, então b vem na frente."""
        rankings = [
            [trecho("a", 0.99), trecho("b", 0.50)],
            [trecho("c", 0.98), trecho("b", 0.50)],
        ]
        self.assertEqual([t.chunk_id for t in fundir_por_rrf(rankings)], ["b", "a", "c"])

    def test_deduplica_por_chunk_id(self):
        rankings = [[trecho("a")], [trecho("a")], [trecho("a")]]
        self.assertEqual(len(fundir_por_rrf(rankings)), 1)

    def test_preserva_a_melhor_similaridade_original(self):
        fundidos = fundir_por_rrf([[trecho("a", 0.40)], [trecho("a", 0.80)]])
        self.assertAlmostEqual(fundidos[0].score, 0.80)

    def test_ranking_unico_preserva_a_ordem(self):
        rankings = [[trecho("a", 0.9), trecho("b", 0.8), trecho("c", 0.7)]]
        self.assertEqual([t.chunk_id for t in fundir_por_rrf(rankings)], ["a", "b", "c"])

    def test_sem_rankings_devolve_vazio(self):
        self.assertEqual(fundir_por_rrf([]), [])
        self.assertEqual(fundir_por_rrf([[], []]), [])

    def test_empate_e_desfeito_de_forma_estavel(self):
        rankings = [[trecho("a", 0.5)], [trecho("b", 0.9)]]
        primeira = [t.chunk_id for t in fundir_por_rrf(rankings)]
        self.assertEqual(primeira, [t.chunk_id for t in fundir_por_rrf(rankings)])
        self.assertEqual(primeira[0], "b", "empate deveria ir para a maior similaridade")


class TestDiversidade(unittest.TestCase):
    def test_teto_por_documento(self):
        trechos = [trecho(f"t{n}", documento="mesmo.txt") for n in range(4)] + [trecho("outro", documento="outro.txt")]
        limitados = limitar_por_documento(trechos, 2)
        self.assertEqual([t.chunk_id for t in limitados], ["t0", "t1", "outro"])

    def test_teto_zero_nao_limita(self):
        trechos = [trecho(f"t{n}", documento="mesmo.txt") for n in range(4)]
        self.assertEqual(len(limitar_por_documento(trechos, 0)), 4)


class TestIntermediador(unittest.TestCase):
    def test_cumpre_o_protocolo_de_recuperacao(self):
        intermediador = montar(GeradorRoteirizado(), RecuperadorFalso())
        self.assertIsInstance(intermediador, RecuperadorDeTrechos)

    def test_decompoe_e_busca_cada_subconsulta(self):
        gerador = GeradorRoteirizado(["quem são os argonianos\no que são os hist"])
        recuperador = RecuperadorFalso(padrao=[trecho("a")])
        intermediador = montar(gerador, recuperador, incluir_pergunta_original=True)

        intermediador.buscar(PERGUNTA)

        consultadas = [consulta for consulta, _ in recuperador.consultas]
        self.assertEqual(consultadas, [PERGUNTA, "quem são os argonianos", "o que são os hist"])

    def test_desligada_repassa_direto_sem_chamar_o_modelo(self):
        gerador = GeradorRoteirizado(["não deveria ser chamado"])
        recuperador = RecuperadorFalso(padrao=[trecho("a")])
        intermediador = montar(gerador, recuperador, ligada=False)

        intermediador.buscar(PERGUNTA, k=7)

        self.assertEqual(gerador.prompts, [])
        self.assertEqual(recuperador.consultas, [(PERGUNTA, 7)])

    def test_pergunta_curta_nao_paga_uma_chamada_ao_modelo(self):
        gerador = GeradorRoteirizado(["não deveria ser chamado"])
        recuperador = RecuperadorFalso(padrao=[trecho("a")])
        intermediador = montar(gerador, recuperador, minimo_de_caracteres=25)

        consulta = intermediador.decompor("quem é Ysgramor?")

        self.assertEqual(gerador.prompts, [])
        self.assertFalse(consulta.veio_do_modelo)
        self.assertIn("curta", consulta.motivo_do_fallback)

    def test_gerador_fora_do_ar_nao_derruba_a_busca(self):
        """A recuperação precisa continuar avaliável sem o modelo de geração."""
        gerador = GeradorRoteirizado(erro=ErroConexao("Ollama fora do ar"))
        recuperador = RecuperadorFalso(padrao=[trecho("a")])
        intermediador = montar(gerador, recuperador)

        resultado = intermediador.buscar(PERGUNTA, k=2)

        self.assertEqual(recuperador.consultas, [(PERGUNTA, 2)])
        self.assertEqual([t.chunk_id for t in resultado], ["a"])

    def test_saida_ilegivel_do_modelo_vira_busca_direta(self):
        gerador = GeradorRoteirizado(["...\n?\n"])
        recuperador = RecuperadorFalso(padrao=[trecho("a")])
        intermediador = montar(gerador, recuperador)

        intermediador.buscar(PERGUNTA, k=4)

        self.assertEqual(recuperador.consultas, [(PERGUNTA, 4)], "fallback deve ser uma busca só, igual à direta")

    def test_avisa_a_interface_antes_de_buscar(self):
        vistas: list[ConsultaDecomposta] = []
        gerador = GeradorRoteirizado(["uma consulta razoável\noutra consulta razoável"])
        intermediador = IntermediadorDeConsulta(
            RecuperadorFalso(padrao=[trecho("a")]),
            gerador,
            ConfigIntermediacao(),
            ConfigBusca(),
            ao_decompor=vistas.append,
        )

        intermediador.buscar(PERGUNTA)

        self.assertEqual(len(vistas), 1)
        self.assertTrue(vistas[0].houve_decomposicao)
        self.assertEqual(vistas[0].original, PERGUNTA)

    def test_orientacao_do_marco_chega_ao_prompt(self):
        gerador = GeradorRoteirizado(["uma consulta razoável"])
        intermediador = IntermediadorDeConsulta(
            RecuperadorFalso(),
            gerador,
            ConfigIntermediacao(),
            ConfigBusca(),
            orientacao_do_marco="procure sempre a posição contrária",
        )

        intermediador.decompor(PERGUNTA)

        self.assertIn("procure sempre a posição contrária", gerador.prompts[0])

    def test_corta_no_k_pedido(self):
        gerador = GeradorRoteirizado(["primeira consulta razoável\nsegunda consulta razoável"])
        recuperador = RecuperadorFalso(padrao=[trecho(f"t{n}") for n in range(10)])
        intermediador = montar(gerador, recuperador)

        self.assertEqual(len(intermediador.buscar(PERGUNTA, k=2)), 2)

    def test_sem_k_usa_o_da_configuracao_de_busca(self):
        gerador = GeradorRoteirizado(["primeira consulta razoável\nsegunda consulta razoável"])
        recuperador = RecuperadorFalso(padrao=[trecho(f"t{n}") for n in range(10)])
        intermediador = montar(gerador, recuperador)  # ConfigBusca(k=3)

        self.assertEqual(len(intermediador.buscar(PERGUNTA)), 3)

    def test_fecha_o_ciclo_rag_sem_o_motor_saber_da_camada(self):
        gerador_da_resposta = GeradorFalso()
        intermediador = montar(
            GeradorRoteirizado(["primeira consulta razoável\nsegunda consulta razoável"]),
            RecuperadorFalso(padrao=[trecho("a")]),
        )

        resposta = MotorRag(intermediador, gerador_da_resposta).responder(PERGUNTA)

        self.assertEqual(resposta.texto, "resposta gerada")
        self.assertEqual([t.chunk_id for t in resposta.trechos], ["a"])


if __name__ == "__main__":
    unittest.main()
