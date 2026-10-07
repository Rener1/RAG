"""
Configuração persistida em `config.toml`.

O que estes testes protegem é a precedência — padrões do código, depois o
arquivo, depois as flags. Inverter as duas últimas é o erro mais fácil de
cometer e o mais difícil de perceber: `--colecao outra` simplesmente não faria
efeito numa máquina que tem `config.toml`, sem mensagem nenhuma.
"""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from apoio import *  # noqa: F401,F403  — põe src/ no sys.path

from rag import config as configuracao  # noqa: E402
from rag.config import Config  # noqa: E402
from rag.erros import ErroConfiguracao  # noqa: E402
from rag.interface import cli  # noqa: E402


def escrever(pasta: str, conteudo: str) -> Path:
    caminho = Path(pasta) / "config.toml"
    caminho.write_text(conteudo, encoding="utf-8")
    return caminho


class TestDiferencas(unittest.TestCase):
    def test_configuracao_intocada_nao_tem_diferencas(self):
        self.assertEqual(configuracao.diferencas(Config()), {})

    def test_so_o_que_mudou_aparece(self):
        config = Config()
        config.busca.k = 9
        self.assertEqual(configuracao.diferencas(config), {"busca": {"k": 9}})

    def test_voltar_ao_padrao_some_das_diferencas(self):
        config = Config()
        config.busca.k = 9
        config.busca.k = Config().busca.k
        self.assertEqual(configuracao.diferencas(config), {})


class TestIdaEVolta(unittest.TestCase):
    def test_salvar_e_carregar_preserva_os_valores(self):
        with tempfile.TemporaryDirectory() as pasta:
            original = Config()
            original.vetorial.colecao = "corpus_ipf"
            original.busca.k = 8
            original.busca.score_minimo = 0.42
            original.geracao.streaming = False
            original.caminhos.dados = Path(pasta) / "dados"

            alvo = configuracao.salvar(original, Path(pasta) / "config.toml")
            carregada = configuracao.carregar(alvo)

            self.assertEqual(carregada.config.vetorial.colecao, "corpus_ipf")
            self.assertEqual(carregada.config.busca.k, 8)
            self.assertAlmostEqual(carregada.config.busca.score_minimo, 0.42)
            self.assertFalse(carregada.config.geracao.streaming)
            self.assertEqual(carregada.config.caminhos.dados, Path(pasta) / "dados")
            self.assertEqual(carregada.avisos, [])

    def test_o_arquivo_gravado_so_tem_as_diferencas(self):
        with tempfile.TemporaryDirectory() as pasta:
            config = Config()
            # Um valor que não pode ser o padrão, senão o teste passa por engano
            # quando o padrão mudar para ele.
            config.busca.k = 11
            self.assertNotEqual(Config().busca.k, 11, "escolha outro valor: este virou o padrão")
            texto = configuracao.salvar(config, Path(pasta) / "config.toml").read_text(encoding="utf-8")

            self.assertIn("[busca]", texto)
            self.assertIn("k = 11", texto)
            self.assertNotIn("[embedding]", texto)
            self.assertNotIn("score_minimo", texto)

    def test_arquivo_ausente_devolve_os_padroes(self):
        with tempfile.TemporaryDirectory() as pasta:
            carregada = configuracao.carregar(Path(pasta) / "nao_existe.toml")
            self.assertEqual(carregada.config, Config())
            self.assertIsNone(carregada.caminho)
            self.assertEqual(carregada.avisos, [])

    def test_sem_arquivo_ignora_o_que_esta_em_disco(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = escrever(pasta, "[busca]\nk = 99\n")
            carregada = configuracao.carregar(caminho, usar_arquivo=False)
            self.assertEqual(carregada.config.busca.k, Config().busca.k)


class TestValidacao(unittest.TestCase):
    def test_secao_desconhecida_vira_aviso_e_nao_erro(self):
        with tempfile.TemporaryDirectory() as pasta:
            carregada = configuracao.carregar(escrever(pasta, "[inventada]\nx = 1\n"))
            self.assertEqual(carregada.config, Config())
            self.assertTrue(any("inventada" in aviso for aviso in carregada.avisos))

    def test_campo_desconhecido_vira_aviso_e_nao_erro(self):
        with tempfile.TemporaryDirectory() as pasta:
            carregada = configuracao.carregar(escrever(pasta, "[busca]\nk = 7\ninventado = 1\n"))
            self.assertEqual(carregada.config.busca.k, 7)
            self.assertTrue(any("busca.inventado" in aviso for aviso in carregada.avisos))

    def test_tipo_errado_e_erro_que_nomeia_o_campo(self):
        with tempfile.TemporaryDirectory() as pasta:
            with self.assertRaises(ErroConfiguracao) as capturado:
                configuracao.carregar(escrever(pasta, '[busca]\nk = "muitos"\n'))
            self.assertIn("busca.k", str(capturado.exception))

    def test_booleano_num_campo_numerico_nao_passa_como_um(self):
        with tempfile.TemporaryDirectory() as pasta:
            with self.assertRaises(ErroConfiguracao):
                configuracao.carregar(escrever(pasta, "[busca]\nk = true\n"))

    def test_toml_invalido_e_erro_explicado(self):
        with tempfile.TemporaryDirectory() as pasta:
            with self.assertRaises(ErroConfiguracao) as capturado:
                configuracao.carregar(escrever(pasta, "[busca\nk = 5\n"))
            self.assertTrue(capturado.exception.sugestao)

    def test_booleano_aceita_o_literal_do_toml_e_o_texto_do_menu(self):
        config = Config()
        self.assertFalse(config.definir("geracao", "streaming", False))
        self.assertTrue(config.definir("geracao", "streaming", "sim"))


class TestPrecedencia(unittest.TestCase):
    """padrão < arquivo < flag — nesta ordem, e a origem é reportável."""

    def test_arquivo_vence_o_padrao_e_a_flag_vence_o_arquivo(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = escrever(pasta, '[vetorial]\ncolecao = "do_arquivo"\n\n[busca]\nk = 7\n')
            carregada = configuracao.carregar(caminho)
            self.assertEqual(carregada.config.vetorial.colecao, "do_arquivo")

            # É o que `--colecao` faz em cli._aplicar_opcoes_globais.
            carregada.config.vetorial.colecao = "da_flag"

            origens = configuracao.origem_dos_valores(carregada)
            self.assertEqual(origens[("vetorial", "colecao")], "flag")
            self.assertEqual(origens[("busca", "k")], "arquivo")
            self.assertEqual(origens[("busca", "score_minimo")], "padrão")

    def test_valor_do_arquivo_igual_ao_padrao_conta_como_arquivo(self):
        with tempfile.TemporaryDirectory() as pasta:
            padrao = Config().busca.k
            carregada = configuracao.carregar(escrever(pasta, f"[busca]\nk = {padrao}\n"))
            self.assertEqual(configuracao.origem_dos_valores(carregada)[("busca", "k")], "arquivo")


class TestSerializacao(unittest.TestCase):
    def test_texto_com_aspas_e_barra_sobrevive(self):
        with tempfile.TemporaryDirectory() as pasta:
            config = Config()
            config.download.user_agent = 'agente "esquisito" com \\barra'
            alvo = configuracao.salvar(config, Path(pasta) / "config.toml")
            self.assertEqual(configuracao.carregar(alvo).config.download.user_agent, config.download.user_agent)


class TestFlagsGlobais(unittest.TestCase):
    """As flags globais valem antes e depois do subcomando.

    Regressão: `parents=[globais]` faz o subparser parsear num namespace novo e
    copiar tudo por cima, então `main.py --colecao x buscar ...` perdia a flag
    sem erro nenhum. `default=SUPPRESS` conserta — e `parser.set_defaults` o
    desfaz, porque reescreve o default do objeto da ação, que é compartilhado.
    """

    def analisar(self, argv: list[str]):
        argumentos = cli.construir_parser().parse_args(argv)
        cli._normalizar_globais(argumentos)
        return argumentos

    def test_colecao_vale_nas_duas_posicoes(self):
        self.assertEqual(self.analisar(["--colecao", "x", "buscar", "p"]).colecao, "x")
        self.assertEqual(self.analisar(["buscar", "p", "--colecao", "x"]).colecao, "x")

    def test_sem_config_vale_nas_duas_posicoes(self):
        self.assertTrue(self.analisar(["--sem-config", "config"]).sem_config)
        self.assertTrue(self.analisar(["config", "--sem-config"]).sem_config)

    def test_carga_e_chunks_valem_nas_duas_posicoes(self):
        self.assertEqual(self.analisar(["--carga", "reduzida", "indexar"]).carga, "reduzida")
        self.assertEqual(self.analisar(["indexar", "--carga", "total"]).carga, "total")
        self.assertEqual(self.analisar(["--chunks", "x.jsonl", "indexar"]).chunks, "x.jsonl")
        self.assertEqual(self.analisar(["avaliar", "--chunks", "x.jsonl"]).chunks, "x.jsonl")

    def test_carga_so_aceita_os_dois_modos(self):
        with self.assertRaises(SystemExit), mock.patch("sys.stderr"):
            self.analisar(["--carga", "0.75", "indexar"])

    def test_carga_e_chunks_chegam_a_configuracao(self):
        config = Config()
        argumentos = self.analisar(
            ["--carga", "reduzida", "--chunks", "exp.jsonl", "chunking", "--tamanho-maximo", "1000"]
        )
        cli._aplicar_opcoes_globais(argumentos, config)
        self.assertEqual(config.carga.modo, "reduzida")
        self.assertEqual(config.caminhos.chunks, config.caminhos.dados / "exp.jsonl")
        self.assertEqual(config.chunking.tamanho_maximo, 1000)

    def test_ausente_cai_no_padrao(self):
        argumentos = self.analisar(["config"])
        self.assertIsNone(argumentos.colecao)
        self.assertIsNone(argumentos.config)
        self.assertFalse(argumentos.sem_config)
        self.assertFalse(argumentos.sem_cor)


class TestExemploVersionado(unittest.TestCase):
    def test_o_exemplo_esta_em_dia_com_as_dataclasses(self):
        """Impede o exemplo de envelhecer quando um campo novo é criado."""
        caminho = Path(__file__).resolve().parents[1] / "config.exemplo.toml"
        self.assertEqual(
            caminho.read_text(encoding="utf-8"),
            configuracao.texto_de_exemplo(),
            "config.exemplo.toml está defasado. Regere com:\n"
            "  python3 -c \"import sys; sys.path.insert(0,'src'); "
            'from rag.config import escrever_exemplo; escrever_exemplo()"',
        )

    def test_o_exemplo_nao_vaza_caminho_absoluto_da_maquina(self):
        self.assertNotIn("/home/", configuracao.texto_de_exemplo())


if __name__ == "__main__":
    unittest.main()
