"""
O limitador de carga.

O que precisa valer: o descanso é proporcional ao trabalho e vem depois dele;
o limite é global, e não por thread; e as peças embrulhadas continuam cumprindo
o protocolo. Relógio e sono são falsos — nenhum teste aqui dorme de verdade.
"""

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from apoio import EmbutidorFalso, GeradorFalso, ReordenadorFalso, RepositorioFalso

from rag.carga import EmbutidorLimitado, GeradorLimitado, LimitadorDeCarga, ReordenadorLimitado
from rag.clientes.ollama import ClienteOllama, GeradorOllama
from rag.config import Config, ConfigEmbedding, ConfigGeracao
from rag.erros import ErroConfiguracao
from rag.modelos import Chunk, TrechoRecuperado
from rag.protocolos import Embutidor, Gerador
from rag.servico import Servico


class RelogioFalso:
    """Relógio que só anda quando o teste manda — inclusive quando "dorme"."""

    def __init__(self) -> None:
        self.agora = 0.0
        self.passo = 0.0  # quanto anda a cada leitura — simula trabalho que leva tempo
        self.sonos: list[float] = []

    def __call__(self) -> float:
        self.agora += self.passo
        return self.agora

    def dormir(self, segundos: float) -> None:
        self.sonos.append(segundos)
        self.agora += segundos


def limitador(fracao: float) -> tuple[LimitadorDeCarga, RelogioFalso]:
    relogio = RelogioFalso()
    return LimitadorDeCarga(fracao, relogio=relogio, dormir=relogio.dormir), relogio


def trabalhar(lim: LimitadorDeCarga, relogio: RelogioFalso, duracao: float) -> None:
    with lim.ocupar():
        relogio.agora += duracao


class TestProporcao(unittest.TestCase):
    def test_fracao_um_nunca_dorme(self):
        lim, relogio = limitador(1.0)
        trabalhar(lim, relogio, 2.0)
        self.assertEqual(relogio.sonos, [])

    def test_metade_descansa_o_mesmo_que_trabalhou(self):
        lim, relogio = limitador(0.5)
        trabalhar(lim, relogio, 0.4)
        self.assertAlmostEqual(relogio.sonos[0], 0.4)

    def test_tres_quartos_descansa_um_terco(self):
        lim, relogio = limitador(0.75)
        trabalhar(lim, relogio, 0.3)
        self.assertAlmostEqual(relogio.sonos[0], 0.1)

    def test_fracao_do_tempo_total_bate_com_a_pedida(self):
        lim, relogio = limitador(0.6)
        for duracao in (0.2, 0.5, 0.1, 0.3):
            trabalhar(lim, relogio, duracao)
        self.assertAlmostEqual(lim.ocupado / relogio.agora, 0.6)

    def test_descansa_mesmo_quando_o_trabalho_falha(self):
        """Um lote que falha também gastou a placa."""
        lim, relogio = limitador(0.5)
        with self.assertRaises(RuntimeError), lim.ocupar():
            relogio.agora += 0.2
            raise RuntimeError("falhou")
        self.assertAlmostEqual(relogio.sonos[0], 0.2)

    def test_fracao_fora_do_intervalo_e_erro(self):
        for invalida in (0, -0.5, 1.5):
            with self.subTest(fracao=invalida), self.assertRaises(ErroConfiguracao):
                LimitadorDeCarga(invalida)


class TestGlobal(unittest.TestCase):
    def test_duas_threads_nunca_trabalham_ao_mesmo_tempo(self):
        """Pausa por thread não limita nada: o descanso de uma cobre o trabalho da outra."""
        lim = LimitadorDeCarga(0.5, dormir=lambda s: time.sleep(0.001))
        dentro = 0
        maximo = 0
        trava = threading.Lock()

        def tarefa():
            nonlocal dentro, maximo
            for _ in range(20):
                with lim.ocupar():
                    with trava:
                        dentro += 1
                        maximo = max(maximo, dentro)
                    time.sleep(0.0005)
                    with trava:
                        dentro -= 1

        threads = [threading.Thread(target=tarefa) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(maximo, 1)


def trecho(pagina: str) -> TrechoRecuperado:
    return TrechoRecuperado(texto="t", titulo_pagina=pagina, documento_origem="d", chunk_id=f"{pagina}::0", score=0.5)


class TestInvolucros(unittest.TestCase):
    def setUp(self):
        self.lim, self.relogio = limitador(0.5)
        self.relogio.passo = 0.1

    def test_embutidor_continua_cumprindo_o_protocolo(self):
        embrulhado = EmbutidorLimitado(EmbutidorFalso(dimensao=4), self.lim)
        self.assertIsInstance(embrulhado, Embutidor)
        self.assertEqual(embrulhado.dimensao, 4)
        self.assertEqual(len(embrulhado.embutir(["a", "b"])), 2)
        self.assertEqual(len(self.relogio.sonos), 1)

    def test_atributo_nao_limitado_passa_direto(self):
        falso = EmbutidorFalso()
        embrulhado = EmbutidorLimitado(falso, self.lim)
        embrulhado.embutir(["x"])
        self.assertIs(embrulhado.chamadas, falso.chamadas)

    def test_reordenador_devolve_a_mesma_ordem(self):
        embrulhado = ReordenadorLimitado(ReordenadorFalso(preferencia=["B"]), self.lim)
        ordem = [t.titulo_pagina for t in embrulhado.reordenar("p", [trecho("A"), trecho("B")])]
        self.assertEqual(ordem, ["B", "A"])
        self.assertEqual(len(self.relogio.sonos), 1)

    def test_gerador_entrega_os_mesmos_pedacos_e_descansa_depois(self):
        embrulhado = GeradorLimitado(GeradorFalso(), self.lim)
        self.assertIsInstance(embrulhado, Gerador)
        self.assertEqual(list(embrulhado.gerar("p")), ["resposta ", "gerada"])
        self.assertEqual(len(self.relogio.sonos), 1)


class TestFiacao(unittest.TestCase):
    """O serviço só embrulha com a carga limitada, e com um limitador só."""

    def test_sem_limite_nada_e_embrulhado(self):
        servico = Servico(Config())
        self.assertIsNone(servico.limitador)
        self.assertNotIsInstance(servico.embutidor, EmbutidorLimitado)
        self.assertNotIsInstance(servico.gerador_de_apoio, GeradorLimitado)

    def test_com_limite_as_pecas_compartilham_o_limitador(self):
        config = Config()
        config.carga.fracao = 0.75
        servico = Servico(config)
        self.assertIsInstance(servico.embutidor, EmbutidorLimitado)
        self.assertIsInstance(servico.gerador_de_apoio, GeradorLimitado)
        self.assertIs(servico.embutidor._limitador, servico.gerador_de_apoio._limitador)

    def test_a_resposta_final_nao_e_limitada(self):
        """Uma rajada só por pergunta — descansar depois dela não poupa nada."""
        config = Config()
        config.carga.fracao = 0.5
        self.assertNotIsInstance(Servico(config).gerador, GeradorLimitado)

    def test_com_limite_a_indexacao_usa_o_lote_menor(self):
        """Pausa por lote: lote menor é pausa mais fina."""
        with tempfile.TemporaryDirectory() as pasta:
            config = Config()
            config.caminhos.dados = Path(pasta)
            config.carga.fracao = 0.99
            with (Path(pasta) / "chunks.jsonl").open("w", encoding="utf-8") as f:
                for i in range(20):
                    f.write(json.dumps(Chunk(f"d::{i}", f"texto {i}", "d", "D", i).como_dicionario()) + "\n")

            servico = Servico(config)
            falso = EmbutidorFalso()
            servico.__dict__["embutidor"] = falso
            servico.__dict__["repositorio"] = RepositorioFalso()
            resultado = servico.indexar()

        self.assertEqual(resultado.processados, 20)
        self.assertEqual(max(len(lote) for lote in falso.chamadas), config.carga.tamanho_lote)


class SessaoFalsa:
    """Guarda o corpo enviado e responde como o Ollama responderia."""

    def __init__(self, resposta: dict) -> None:
        self.resposta = resposta
        self.corpos: list[dict] = []

    def post(self, url, json, timeout, stream=False):
        self.corpos.append(json)
        resposta = self.resposta

        class Resposta:
            def raise_for_status(self):
                pass

            def json(self):
                return resposta

        return Resposta()


class TestThreadsDeCpu(unittest.TestCase):
    """Com o modelo na GPU, as threads de CPU do Ollama só esperam — e esquentam."""

    def embutir_com(self, threads: int) -> dict:
        cliente = ClienteOllama(ConfigEmbedding(), threads)
        cliente._sessao = SessaoFalsa({"embeddings": [[0.0]]})
        cliente.embutir(["x"])
        return cliente._sessao.corpos[0]

    def test_zero_deixa_o_ollama_decidir(self):
        self.assertNotIn("options", self.embutir_com(0))

    def test_embedding_leva_num_thread(self):
        self.assertEqual(self.embutir_com(2)["options"], {"num_thread": 2})

    def test_geracao_leva_num_thread_sem_perder_as_outras_opcoes(self):
        gerador = GeradorOllama(ConfigGeracao(streaming=False), 2)
        gerador._sessao = SessaoFalsa({"response": "ok"})
        self.assertEqual(list(gerador.gerar("p")), ["ok"])
        opcoes = gerador._sessao.corpos[0]["options"]
        self.assertEqual(opcoes["num_thread"], 2)
        self.assertIn("num_ctx", opcoes)


if __name__ == "__main__":
    unittest.main()
