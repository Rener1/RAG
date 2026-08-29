"""
A sessão dialógica.

Dois pontos concentram o risco. O primeiro é o atalho: uma dúvida factual não
pode passar pela problematização, senão perguntar "o que é X" vira uma
negociação e ninguém usa o sistema. O segundo é a consulta consolidada: o que a
pessoa responde precisa mesmo chegar à recuperação — se não chegar, a
problematização vira teatro, custando tempo e não melhorando resposta nenhuma.
"""

import unittest

from apoio import GeradorFalso, GeradorRoteirizado, MarcoFalso, RecuperadorFalso  # noqa: F401

from rag.config import ConfigSessao  # noqa: E402
from rag.erros import ErroConexao  # noqa: E402
from rag.modelos import EstadoDaSessao, TipoDeDemanda, TrechoRecuperado  # noqa: E402
from rag.orquestrador import MotorRag  # noqa: E402
from rag.sessao import (  # noqa: E402
    Dialogo,
    classificar_por_pistas,
    extrair_perguntas,
    ler_demanda,
)

DEMANDA = "escreva um plano de alfabetização para o município X"
FACTUAL = "o que é um tema gerador?"


def trecho(identificador: str = "a") -> TrechoRecuperado:
    return TrechoRecuperado(
        texto=f"texto {identificador}",
        titulo_pagina=identificador,
        documento_origem=f"{identificador}.txt",
        chunk_id=identificador,
        score=0.9,
    )


def montar(respostas: list[str], recuperador=None, marco=None, **ajustes):
    """Diálogo com dublês. Devolve (dialogo, gerador_de_apoio, recuperador)."""
    recuperador = recuperador or RecuperadorFalso(padrao=[trecho()])
    gerador = GeradorRoteirizado(respostas)
    motor = MotorRag(recuperador, GeradorFalso())
    return Dialogo(motor, gerador, ConfigSessao(**ajustes), marco), gerador, recuperador


class TestHeuristica(unittest.TestCase):
    def test_reconhece_pedido_de_produto(self):
        for pergunta in ("escreva um relatório", "monte um plano de aula", "elabore uma minuta"):
            self.assertIs(classificar_por_pistas(pergunta), TipoDeDemanda.PRODUTO_ACABADO)

    def test_reconhece_duvida_factual(self):
        for pergunta in ("o que é práxis?", "quem foi Paulo Freire?", "quando isso aconteceu?"):
            self.assertIs(classificar_por_pistas(pergunta), TipoDeDemanda.DUVIDA_FACTUAL)

    def test_o_que_nao_reconhece_fica_indefinido(self):
        self.assertIs(classificar_por_pistas("me fale sobre o assunto"), TipoDeDemanda.INDEFINIDO)

    def test_produto_vence_pergunta_factual_embutida(self):
        """'escreva sobre o que é X' continua sendo pedido de produto."""
        self.assertIs(classificar_por_pistas("escreva sobre o que é práxis"), TipoDeDemanda.PRODUTO_ACABADO)


class TestLeituraDaDemanda(unittest.TestCase):
    def test_le_a_palavra_do_modelo(self):
        self.assertIs(ler_demanda("duvida_factual"), TipoDeDemanda.DUVIDA_FACTUAL)
        self.assertIs(ler_demanda("  Produto Acabado.  "), TipoDeDemanda.PRODUTO_ACABADO)

    def test_saida_irreconhecivel_fica_indefinida(self):
        self.assertIs(ler_demanda("não sei dizer"), TipoDeDemanda.INDEFINIDO)
        self.assertIs(ler_demanda(""), TipoDeDemanda.INDEFINIDO)


class TestExtracaoDePerguntas(unittest.TestCase):
    def test_linha_sem_interrogacao_nao_e_pergunta(self):
        saida = "Aqui estão as perguntas:\nQuem são os sujeitos?\nvou pensar mais"
        self.assertEqual(extrair_perguntas(saida, 3), ["Quem são os sujeitos?"])

    def test_tira_numeracao_e_repetidas(self):
        saida = "1. Quem são os sujeitos?\n2. quem são os sujeitos?\n- Que território?"
        self.assertEqual(extrair_perguntas(saida, 3), ["Quem são os sujeitos?", "Que território?"])

    def test_respeita_o_maximo(self):
        saida = "\n".join(f"Pergunta número {n} sobre o tema?" for n in range(8))
        self.assertEqual(len(extrair_perguntas(saida, 2)), 2)


class TestTriagem(unittest.TestCase):
    def test_duvida_factual_atalha_direto_para_a_busca(self):
        dialogo, gerador, _ = montar(["duvida_factual", "não deveria problematizar"])
        sessao = dialogo.iniciar(FACTUAL)

        dialogo.classificar(sessao)

        self.assertIs(sessao.estado, EstadoDaSessao.RECUPERACAO)
        self.assertEqual(dialogo.problematizar(sessao), [])
        self.assertEqual(len(gerador.prompts), 1, "só a triagem deveria ter chamado o modelo")

    def test_produto_acabado_vai_problematizar(self):
        dialogo, _, _ = montar(["produto_acabado"])
        sessao = dialogo.iniciar(DEMANDA)

        self.assertIs(dialogo.classificar(sessao), TipoDeDemanda.PRODUTO_ACABADO)
        self.assertIs(sessao.estado, EstadoDaSessao.PROBLEMATIZACAO)

    def test_saida_irreconhecivel_cai_na_heuristica(self):
        dialogo, _, _ = montar(["não faço ideia"])
        sessao = dialogo.iniciar(DEMANDA)

        self.assertIs(dialogo.classificar(sessao), TipoDeDemanda.PRODUTO_ACABADO)

    def test_heuristica_vence_o_modelo_em_pedido_de_produto(self):
        """O erro caro é deixar passar um pedido de produto, não problematizar à toa."""
        dialogo, _, _ = montar(["duvida_factual"])
        sessao = dialogo.iniciar(DEMANDA)

        self.assertIs(dialogo.classificar(sessao), TipoDeDemanda.PRODUTO_ACABADO)
        self.assertIs(sessao.estado, EstadoDaSessao.PROBLEMATIZACAO)

    def test_modelo_fora_do_ar_nao_impede_perguntar(self):
        motor = MotorRag(RecuperadorFalso(padrao=[trecho()]), GeradorFalso())
        gerador = GeradorRoteirizado(erro=ErroConexao("Ollama fora do ar"))
        dialogo = Dialogo(motor, gerador, ConfigSessao())
        sessao = dialogo.iniciar(FACTUAL)

        dialogo.classificar(sessao)

        self.assertIs(sessao.demanda, TipoDeDemanda.DUVIDA_FACTUAL, "deveria cair na heurística")
        self.assertIs(sessao.estado, EstadoDaSessao.RECUPERACAO)

    def test_problematizacao_desligada_nao_chama_o_modelo(self):
        dialogo, gerador, _ = montar(["produto_acabado"], problematizar=False)
        sessao = dialogo.iniciar(DEMANDA)

        dialogo.classificar(sessao)

        self.assertEqual(gerador.prompts, [])
        self.assertIs(sessao.estado, EstadoDaSessao.RECUPERACAO)

    def test_marco_pode_desligar_a_problematizacao(self):
        marco = MarcoFalso(metadados={"problematizar": "não"})
        dialogo, _, _ = montar(["produto_acabado"], marco=marco)
        sessao = dialogo.iniciar(DEMANDA)

        dialogo.classificar(sessao)

        self.assertIs(sessao.estado, EstadoDaSessao.RECUPERACAO)

    def test_marco_nao_liga_o_que_a_configuracao_desligou(self):
        marco = MarcoFalso(metadados={"problematizar": "sim"})
        dialogo, _, _ = montar(["produto_acabado"], marco=marco, problematizar=False)
        sessao = dialogo.iniciar(DEMANDA)

        dialogo.classificar(sessao)

        self.assertIs(sessao.estado, EstadoDaSessao.RECUPERACAO)


class TestProblematizacao(unittest.TestCase):
    def test_devolve_perguntas_e_registra_os_turnos(self):
        dialogo, _, _ = montar(["produto_acabado", "Quem são os sujeitos?\nQue território?"])
        sessao = dialogo.iniciar(DEMANDA)
        dialogo.classificar(sessao)

        perguntas = dialogo.problematizar(sessao)

        self.assertEqual(perguntas, ["Quem são os sujeitos?", "Que território?"])
        self.assertEqual(sessao.perguntas_devolvidas(), perguntas)
        self.assertEqual(sessao.rodadas_de_problematizacao, 1)

    def test_modelo_sem_perguntas_segue_para_a_busca(self):
        dialogo, _, _ = montar(["produto_acabado", "nada a perguntar"])
        sessao = dialogo.iniciar(DEMANDA)
        dialogo.classificar(sessao)

        self.assertEqual(dialogo.problematizar(sessao), [])
        self.assertIs(sessao.estado, EstadoDaSessao.RECUPERACAO)

    def test_ancoragem_busca_no_acervo_antes_de_perguntar(self):
        recuperador = RecuperadorFalso(padrao=[trecho()])
        dialogo, gerador, _ = montar(
            ["produto_acabado", "Quem são os sujeitos?"], recuperador=recuperador, perguntas_ancoradas=True
        )
        sessao = dialogo.iniciar(DEMANDA)
        dialogo.classificar(sessao)
        dialogo.problematizar(sessao)

        self.assertEqual(len(recuperador.consultas), 1)
        self.assertIn("texto a", gerador.prompts[-1], "os trechos deveriam ancorar o prompt")

    def test_sem_ancoragem_nao_busca(self):
        recuperador = RecuperadorFalso(padrao=[trecho()])
        dialogo, _, _ = montar(
            ["produto_acabado", "Quem são os sujeitos?"], recuperador=recuperador, perguntas_ancoradas=False
        )
        sessao = dialogo.iniciar(DEMANDA)
        dialogo.classificar(sessao)
        dialogo.problematizar(sessao)

        self.assertEqual(recuperador.consultas, [])

    def test_orientacao_do_marco_chega_ao_prompt(self):
        marco = MarcoFalso({"problematizacao": "pergunte sempre pelo território"})
        dialogo, gerador, _ = montar(["produto_acabado", "Que território?"], marco=marco)
        sessao = dialogo.iniciar(DEMANDA)
        dialogo.classificar(sessao)
        dialogo.problematizar(sessao)

        self.assertIn("pergunte sempre pelo território", gerador.prompts[-1])


class TestRespostasEEscape(unittest.TestCase):
    def test_resposta_encerra_a_rodada_e_vai_buscar(self):
        dialogo, _, _ = montar(["produto_acabado", "Quem são os sujeitos?"], maximo_de_rodadas=1)
        sessao = dialogo.iniciar(DEMANDA)
        dialogo.classificar(sessao)
        dialogo.problematizar(sessao)

        self.assertIs(dialogo.receber(sessao, "jovens e adultos"), EstadoDaSessao.RECUPERACAO)

    def test_segunda_rodada_quando_configurada(self):
        dialogo, _, _ = montar(["produto_acabado", "Quem são os sujeitos?"], maximo_de_rodadas=2)
        sessao = dialogo.iniciar(DEMANDA)
        dialogo.classificar(sessao)
        dialogo.problematizar(sessao)

        self.assertIs(dialogo.receber(sessao, "jovens e adultos"), EstadoDaSessao.PROBLEMATIZACAO)

    def test_linha_vazia_pula(self):
        dialogo, _, _ = montar(["produto_acabado", "Quem são os sujeitos?"])
        sessao = dialogo.iniciar(DEMANDA)
        dialogo.classificar(sessao)
        dialogo.problematizar(sessao)

        self.assertIs(dialogo.receber(sessao, "   "), EstadoDaSessao.RECUPERACAO)
        self.assertEqual(sessao.respostas_da_pessoa(), [])

    def test_palavra_de_escape_pula(self):
        for escape in ("pular", "/responder", "Seguir"):
            dialogo, _, _ = montar(["produto_acabado", "Quem são os sujeitos?"])
            sessao = dialogo.iniciar(DEMANDA)
            dialogo.classificar(sessao)
            dialogo.problematizar(sessao)

            self.assertIs(dialogo.receber(sessao, escape), EstadoDaSessao.RECUPERACAO)

    def test_pular_mantem_o_historico(self):
        dialogo, _, _ = montar(["produto_acabado", "Quem são os sujeitos?"])
        sessao = dialogo.iniciar(DEMANDA)
        dialogo.classificar(sessao)
        dialogo.problematizar(sessao)

        dialogo.pular_problematizacao(sessao)

        self.assertIs(sessao.estado, EstadoDaSessao.RECUPERACAO)
        self.assertEqual(len(sessao.perguntas_devolvidas()), 1)


class TestConsultaConsolidada(unittest.TestCase):
    def test_o_que_a_pessoa_respondeu_chega_a_recuperacao(self):
        """Se isto quebrar, a problematização vira teatro: custa tempo e não melhora a busca."""
        recuperador = RecuperadorFalso(padrao=[trecho()])
        dialogo, _, _ = montar(
            ["produto_acabado", "Quem são os sujeitos?"], recuperador=recuperador, perguntas_ancoradas=False
        )
        sessao = dialogo.iniciar(DEMANDA)
        dialogo.classificar(sessao)
        dialogo.problematizar(sessao)
        dialogo.receber(sessao, "jovens e adultos do bairro Y")

        dialogo.responder(sessao)

        consultada = recuperador.consultas[-1][0]
        self.assertIn(DEMANDA, consultada)
        self.assertIn("jovens e adultos do bairro Y", consultada)

    def test_as_perguntas_do_sistema_ficam_fora_da_consulta(self):
        """Pô-las na busca faria o embedding perseguir o vocabulário da própria máquina."""
        dialogo, _, _ = montar(["produto_acabado", "Quem são os sujeitos?"], perguntas_ancoradas=False)
        sessao = dialogo.iniciar(DEMANDA)
        dialogo.classificar(sessao)
        dialogo.problematizar(sessao)
        dialogo.receber(sessao, "jovens e adultos")

        self.assertNotIn("Quem são os sujeitos?", sessao.consulta_consolidada())


class TestResposta(unittest.TestCase):
    def test_com_trechos_vai_para_resposta(self):
        dialogo, _, _ = montar(["duvida_factual"])
        sessao = dialogo.iniciar(FACTUAL)
        dialogo.classificar(sessao)

        trechos, fluxo = dialogo.responder(sessao)

        self.assertEqual("".join(fluxo), "resposta gerada")
        self.assertEqual(len(trechos), 1)
        self.assertIs(sessao.estado, EstadoDaSessao.RESPOSTA)

    def test_sem_trechos_encerra(self):
        dialogo, _, _ = montar(["duvida_factual"], recuperador=RecuperadorFalso(padrao=[]))
        sessao = dialogo.iniciar(FACTUAL)
        dialogo.classificar(sessao)

        trechos, _ = dialogo.responder(sessao)

        self.assertEqual(trechos, [])
        self.assertIs(sessao.estado, EstadoDaSessao.ENCERRADA)


if __name__ == "__main__":
    unittest.main()
