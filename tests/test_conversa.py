"""
Memória de conversa.

O que precisa valer:

- seguimento sem histórico não custa chamada ao modelo;
- tropeço do modelo vira a pergunta crua, nunca exceção;
- o histórico chega ao prompt da resposta rotulado como contexto, não como fonte;
- o histórico ocupa espaço do orçamento de contexto, de forma visível;
- `/nova` esquece mesmo;
- avaliação com e sem reescrita mede a mesma coisa nos casos avulsos.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from apoio import GeradorFalso, GeradorRoteirizado, RecuperadorFalso

from rag.avaliacao import CasoDeTeste, avaliar, carregar_casos
from rag.config import Config, ConfigConversa
from rag.conversa import Conversa, extrair_reescrita, formatar_historico, montar_prompt_de_reescrita
from rag.erros import ErroConexao
from rag.etapas.geracao import montar_prompt
from rag.interface import acoes, cli
from rag.modelos import TrechoRecuperado, TrocaDaConversa
from rag.orquestrador import MotorRag
from rag.servico import Servico


def trecho(pagina: str, chars: int = 400) -> TrechoRecuperado:
    return TrechoRecuperado(
        texto="x" * chars, titulo_pagina=pagina, documento_origem=f"{pagina}.txt", chunk_id=pagina, score=0.9
    )


def conversa(respostas=None, erro=None, **config) -> tuple[Conversa, GeradorRoteirizado]:
    gerador = GeradorRoteirizado(respostas, erro=erro)
    return Conversa(gerador, ConfigConversa(**config)), gerador


class TestExtrairReescrita(unittest.TestCase):
    def test_linha_simples(self):
        self.assertEqual(
            extrair_reescrita("qual a relação dos argonianos com os Hist?", "e os Hist?"),
            "qual a relação dos argonianos com os Hist?",
        )

    def test_tira_seta_aspas_e_rotulo(self):
        self.assertEqual(extrair_reescrita('-> "quem são os Khajiit?"', "e eles?"), "quem são os Khajiit?")
        self.assertEqual(extrair_reescrita("Reescrita: quem são os Khajiit?", "e eles?"), "quem são os Khajiit?")

    def test_pula_linhas_vazias(self):
        self.assertEqual(extrair_reescrita("\n\n  quem foi Talos?\n", "e ele?"), "quem foi Talos?")

    def test_saida_vazia_nao_serve(self):
        self.assertEqual(extrair_reescrita("   \n", "e ele?"), "")

    def test_saida_muito_maior_e_resposta_e_nao_reescrita(self):
        """O modelo respondendo em vez de reescrever buscaria pior que a pergunta crua."""
        self.assertEqual(extrair_reescrita("x" * 1000, "e eles?"), "")


class TestReescrita(unittest.TestCase):
    def test_primeira_pergunta_nao_chama_o_modelo(self):
        c, gerador = conversa()
        reescrita = c.reescrever("quem são os argonianos?")
        self.assertEqual(reescrita.consulta, "quem são os argonianos?")
        self.assertFalse(reescrita.mudou)
        self.assertEqual(gerador.prompts, [])

    def test_seguimento_e_reescrito_pelo_modelo(self):
        c, gerador = conversa(["qual a relação dos argonianos com os Hist?"])
        c.registrar("quem são os argonianos?", "quem são os argonianos?", "Os argonianos são...")
        reescrita = c.reescrever("e qual a relação deles com os Hist?")

        self.assertEqual(reescrita.consulta, "qual a relação dos argonianos com os Hist?")
        self.assertTrue(reescrita.mudou)
        self.assertTrue(reescrita.veio_do_modelo)
        self.assertIn("quem são os argonianos?", gerador.prompts[0])

    def test_modelo_fora_do_ar_devolve_a_pergunta_crua(self):
        c, _ = conversa(erro=ErroConexao("Ollama fora do ar"))
        c.registrar("p", "p")
        reescrita = c.reescrever("e eles?")
        self.assertEqual(reescrita.consulta, "e eles?")
        self.assertIn("não respondeu", reescrita.motivo)

    def test_saida_inaproveitavel_devolve_a_pergunta_crua(self):
        c, _ = conversa([""])
        c.registrar("p", "p")
        self.assertEqual(c.reescrever("e eles?").consulta, "e eles?")

    def test_a_reescrita_usa_a_consulta_anterior_e_nao_a_pergunta_crua(self):
        """A consulta já resolveu as referências; a pergunta crua acumularia ambiguidade."""
        prompt = montar_prompt_de_reescrita(
            [TrocaDaConversa(pergunta="e eles?", consulta="quem são os Khajiit?")], "de onde vêm?"
        )
        self.assertIn("quem são os Khajiit?", prompt)
        self.assertNotIn("e eles?", prompt)

    def test_so_o_inicio_da_ultima_resposta_entra_na_reescrita(self):
        prompt = montar_prompt_de_reescrita(
            [TrocaDaConversa(pergunta="p", consulta="p", resposta="r" * 5000)], "e o segundo ponto?"
        )
        self.assertLess(prompt.count("r"), 600)

    def test_esquece_o_que_passou_do_limite(self):
        c, _ = conversa(turnos_lembrados=2, turnos_no_prompt=1)
        for numero in range(5):
            c.registrar(f"p{numero}", f"p{numero}")
        self.assertEqual([t.consulta for t in c.trocas], ["p3", "p4"])

    def test_zerar_esquece_tudo(self):
        c, gerador = conversa()
        c.registrar("p", "p")
        c.zerar()
        c.reescrever("e eles?")
        self.assertTrue(c.vazia)
        self.assertEqual(gerador.prompts, [])

    def test_com_perguntas_anteriores_monta_o_historico(self):
        c = Conversa.com_perguntas_anteriores(GeradorFalso(), ConfigConversa(), ["a?", "b?"])
        self.assertEqual([t.consulta for t in c.trocas], ["a?", "b?"])


class TestHistoricoNoPrompt(unittest.TestCase):
    def test_resposta_anterior_vai_truncada(self):
        texto = formatar_historico([TrocaDaConversa("p", "p", "r" * 2000)], caracteres_por_resposta=100)
        self.assertIn("Pergunta: p", texto)
        self.assertLess(texto.count("r"), 150)

    def test_sem_turnos_no_prompt_nao_ha_historico(self):
        c, _ = conversa(turnos_no_prompt=0)
        c.registrar("p", "p", "r")
        self.assertEqual(c.historico_para_o_prompt(), "")

    def test_historico_entra_rotulado_como_contexto_e_nao_como_fonte(self):
        prompt = montar_prompt("e eles?", [trecho("Lore:A")], historico="Pergunta: quem são os Khajiit?")
        self.assertIn("CONVERSA ANTERIOR", prompt)
        self.assertIn("não é fonte", prompt)
        self.assertLess(prompt.index("CONVERSA ANTERIOR"), prompt.index("TRECHOS RECUPERADOS"))

    def test_sem_historico_o_prompt_fica_como_antes(self):
        self.assertEqual(montar_prompt("p", [trecho("Lore:A")]), montar_prompt("p", [trecho("Lore:A")], historico=""))
        self.assertNotIn("CONVERSA ANTERIOR", montar_prompt("p", [trecho("Lore:A")]))

    def test_motor_leva_o_historico_ao_gerador(self):
        gerador = GeradorFalso()
        motor = MotorRag(RecuperadorFalso(padrao=[trecho("Lore:A")]), gerador)
        _, fluxo = motor.responder_em_fluxo("e eles?", historico="Pergunta: quem são os Khajiit?")
        "".join(fluxo)
        self.assertIn("quem são os Khajiit?", gerador.ultimo_prompt)

    def test_montador_de_dois_argumentos_continua_valendo_sem_historico(self):
        gerador = GeradorFalso()
        motor = MotorRag(RecuperadorFalso(padrao=[trecho("Lore:A")]), gerador, lambda p, t: f"CUSTOM {p}")
        _, fluxo = motor.responder_em_fluxo("p")
        "".join(fluxo)
        self.assertEqual(gerador.ultimo_prompt, "CUSTOM p")

    def test_historico_ocupa_espaco_dos_trechos(self):
        """Cada caractere do histórico sai do orçamento dos trechos — à vista."""
        trechos = [trecho(f"Lore:{n}") for n in range(8)]
        motor = MotorRag(RecuperadorFalso(padrao=trechos), GeradorFalso(), orcamento_em_tokens=1200)
        sem = motor.trechos_que_cabem("p", trechos)
        com = motor.trechos_que_cabem("p", trechos, historico="h" * 2000)
        self.assertLess(len(com), len(sem))


class TestAvaliacaoDeConversa(unittest.TestCase):
    def test_carrega_o_historico_do_gabarito(self):
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = Path(pasta) / "casos.jsonl"
            arquivo.write_text(
                json.dumps({"id": "c1", "historico": ["a?"], "demanda": "e b?", "paginas_esperadas": ["Lore:B"]}),
                encoding="utf-8",
            )
            caso = carregar_casos(arquivo)[0]
        self.assertEqual(caso.historico, ("a?",))

    def test_o_gabarito_versionado_carrega(self):
        casos = carregar_casos(Path(__file__).resolve().parents[1] / "avaliacao" / "casos_conversa.jsonl")
        self.assertTrue(all(caso.historico for caso in casos))

    def test_reescrita_muda_o_que_vai_a_busca_so_nos_seguimentos(self):
        recuperador = RecuperadorFalso(padrao=[trecho("Lore:B")])
        casos = [
            CasoDeTeste("c1", "e b?", ("Lore:B",), historico=("a?",)),
            CasoDeTeste("c2", "avulsa?", ("Lore:B",)),
        ]
        resultado = avaliar(
            casos, recuperador, k=3, reescrever=lambda historico, pergunta: f"{historico[-1]} {pergunta}"
        )

        self.assertEqual([c for c, _ in recuperador.consultas], ["a? e b?", "avulsa?"])
        self.assertEqual(resultado.resultados[0].consulta, "a? e b?")
        self.assertEqual(resultado.resultados[1].consulta, "")


class TestFiacao(unittest.TestCase):
    def test_memoria_desligada_nao_cria_conversa(self):
        config = Config()
        config.conversa.ligada = False
        self.assertIsNone(Servico(config).nova_conversa())

    def test_cada_conversa_e_nova(self):
        servico = Servico(Config())
        self.assertIsNot(servico.nova_conversa(), servico.nova_conversa())

    def test_sem_memoria_desliga_pela_cli(self):
        config = Config()
        argumentos = cli.construir_parser().parse_args(["perguntar", "--sem-memoria"])
        cli._normalizar_globais(argumentos)
        cli._aplicar_opcoes_globais(argumentos, config)
        self.assertFalse(config.conversa.ligada)

    def test_laco_passa_a_mesma_conversa_e_nova_zera(self):
        servico = Servico(Config())
        recebidas = []

        def executar_uma(servico, pergunta, k=None, conversa=None):
            recebidas.append((pergunta, conversa))
            conversa.registrar(pergunta, pergunta)
            return True

        linhas = iter(["quem são os Khajiit?", "e de onde vêm?", acoes.COMANDO_NOVA_CONVERSA, "outra coisa?", ""])
        with mock.patch.object(acoes.console, "perguntar", side_effect=lambda *a, **k: next(linhas)):
            with mock.patch.object(acoes.console, "detalhe"), mock.patch.object(acoes.console, "info"):
                self.assertTrue(acoes.acao_conversar(servico, executar_uma))

        primeira, segunda, terceira = (conversa for _, conversa in recebidas)
        self.assertIs(primeira, segunda)
        self.assertIsNot(segunda, terceira)
        self.assertEqual([t.pergunta for t in terceira.trocas], ["outra coisa?"])


if __name__ == "__main__":
    unittest.main()
