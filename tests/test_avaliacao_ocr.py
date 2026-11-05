"""Testes da avaliação do OCR — métricas, leitura das pastas e geração com motor de mentira."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from apoio import ReconhecedorFalso

from rag import avaliacao_ocr
from rag.clientes import pdf as clientes_pdf
from rag.clientes.pdf import confianca_media_do_tsv
from rag.config import ConfigKraken, ConfigRegioes
from rag.erros import ErroConfiguracao
from rag.modelos import LeituraDoMotor


class TestDistanciaDeEdicao(unittest.TestCase):
    def test_caso_classico(self):
        self.assertEqual(avaliacao_ocr.distancia_de_edicao("kitten", "sitting"), 3)

    def test_iguais_e_vazios(self):
        self.assertEqual(avaliacao_ocr.distancia_de_edicao("abc", "abc"), 0)
        self.assertEqual(avaliacao_ocr.distancia_de_edicao("", "abc"), 3)
        self.assertEqual(avaliacao_ocr.distancia_de_edicao("abc", ""), 3)

    def test_vale_para_listas_de_palavras(self):
        self.assertEqual(avaliacao_ocr.distancia_de_edicao(["a", "b", "c"], ["a", "x", "c"]), 1)


class TestMetricas(unittest.TestCase):
    def test_cer_ignora_quebra_de_linha_e_espaco(self):
        """O motor não é punido por quebrar a linha noutro lugar."""
        self.assertEqual(avaliacao_ocr.cer("educação  popular\né", "educação popular é"), 0.0)

    def test_cer_conta_letra_trocada(self):
        self.assertAlmostEqual(avaliacao_ocr.cer("reunião", "reuni&o"), 1 / 7)

    def test_pagina_vazia_da_cer_total(self):
        """É o P1: página legível que sai vazia."""
        self.assertEqual(avaliacao_ocr.cer("texto legível", ""), 1.0)

    def test_referencia_vazia(self):
        self.assertEqual(avaliacao_ocr.cer("", ""), 0.0)
        self.assertEqual(avaliacao_ocr.cer("", "lixo"), 1.0)

    def test_wer_conta_palavras(self):
        self.assertAlmostEqual(avaliacao_ocr.wer("a leitura do mundo", "a leltura do mundo"), 1 / 4)

    def test_texto_so_fora_de_ordem(self):
        """WER alto e WER sem ordem zero: a diferença é o problema de ordem (P6, P11)."""
        referencia, candidato = "um dois três quatro", "três quatro um dois"
        self.assertGreater(avaliacao_ocr.wer(referencia, candidato), 0.5)
        self.assertEqual(avaliacao_ocr.wer_sem_ordem(referencia, candidato), 0.0)

    def test_troca_conta_igual_com_e_sem_ordem(self):
        referencia, candidato = "a leitura do mundo", "a leltura do mundo"
        self.assertEqual(avaliacao_ocr.wer(referencia, candidato), avaliacao_ocr.wer_sem_ordem(referencia, candidato))

    def test_espaco_depois_da_virgula_nao_e_erro_de_leitura(self):
        """Datiloscrito sem espaço depois da vírgula contra leitura com espaço."""
        referencia, candidato = "Professores,quer pretenda", "Professores, quer pretenda"
        self.assertGreater(avaliacao_ocr.wer(referencia, candidato), 0)
        self.assertEqual(avaliacao_ocr.wer_pontuacao_separada(referencia, candidato), 0.0)

    def test_fora_do_dicionario(self):
        def verificador(palavras, idioma):
            return {"educacão"}

        fracao = avaliacao_ocr.fracao_fora_do_dicionario("A educacão, 1957.", "por", verificador)
        self.assertEqual(fracao, 0.5)  # "1957" não é só letras e fica fora da conta

    def test_sem_dicionario_o_indicador_some(self):
        self.assertIsNone(avaliacao_ocr.fracao_fora_do_dicionario("texto", "spa", lambda p, i: None))
        self.assertIsNone(avaliacao_ocr.fracao_fora_do_dicionario("texto", "por", None))


class TestIdentificador(unittest.TestCase):
    def test_leva_handle_arquivo_e_pagina(self):
        self.assertEqual(
            avaliacao_ocr.identificador("7891/90109", "FPF_OPF_01_0005.pdf", 3), "7891_90109_FPF_OPF_01_0005_p0003"
        )


class TestPastas(unittest.TestCase):
    def setUp(self):
        self._temporario = tempfile.TemporaryDirectory()
        self.base = Path(self._temporario.name)
        (self.base / "referencias").mkdir()
        (self.base / "referencias" / "doc_p0001.txt").write_text("a leitura do mundo", encoding="utf-8")
        (self.base / "referencias" / "doc_p0002.txt").write_text("precede a palavra", encoding="utf-8")

    def tearDown(self):
        self._temporario.cleanup()

    def candidato(self, motor, pagina, texto, registro=None):
        pasta = self.base / "candidatos" / motor
        pasta.mkdir(parents=True, exist_ok=True)
        (pasta / f"{pagina}.txt").write_text(texto, encoding="utf-8")
        if registro is not None:
            (pasta / f"{pagina}.json").write_text(json.dumps(registro), encoding="utf-8")

    def test_compara_cada_candidato_com_a_referencia(self):
        self.candidato("bom", "doc_p0001", "a leitura do mundo", {"tempo_s": 1.5})
        self.candidato("bom", "doc_p0002", "precede a palavra")
        resultados, avisos = avaliacao_ocr.avaliar(self.base)
        self.assertEqual([r.cer for r in resultados], [0.0, 0.0])
        self.assertEqual(resultados[0].tempo_s, 1.5)
        self.assertEqual(avisos, [])

    def test_candidato_ausente_vira_aviso(self):
        self.candidato("parcial", "doc_p0001", "a leitura do mundo")
        resultados, avisos = avaliacao_ocr.avaliar(self.base)
        self.assertEqual(len(resultados), 1)
        self.assertEqual(avisos, ["parcial: sem candidato para doc_p0002"])

    def test_sem_referencia_e_erro_explicado(self):
        with self.assertRaises(ErroConfiguracao):
            avaliacao_ocr.avaliar(self.base / "vazia")

    def test_media_por_motor_pesa_paginas_igual(self):
        self.candidato("m", "doc_p0001", "a leitura do mundo")  # CER 0
        self.candidato("m", "doc_p0002", "")  # CER 1
        resultados, _ = avaliacao_ocr.avaliar(self.base)
        self.assertEqual(avaliacao_ocr.media_por_motor(resultados)["m"]["cer"], 0.5)


class TestGerarCandidatos(unittest.TestCase):
    def setUp(self):
        self._temporario = tempfile.TemporaryDirectory()
        self.base = Path(self._temporario.name)
        self.paginas = [
            avaliacao_ocr.PaginaDeTeste("doc_p0001", Path("doc.pdf"), 1, "por"),
            avaliacao_ocr.PaginaDeTeste("doc_p0002", Path("doc.pdf"), 2, "eng"),
        ]

    def tearDown(self):
        self._temporario.cleanup()

    def test_grava_texto_e_registro(self):
        def motor(pdf, pagina, idioma):
            return LeituraDoMotor(f"página {pagina} em {idioma}", 91.0)

        avisos = avaliacao_ocr.gerar_candidatos({"falso": motor}, self.paginas, self.base)
        pasta = self.base / "candidatos" / "falso"
        self.assertEqual(avisos, [])
        self.assertEqual((pasta / "doc_p0002.txt").read_text(encoding="utf-8"), "página 2 em eng")
        registro = json.loads((pasta / "doc_p0002.json").read_text(encoding="utf-8"))
        self.assertEqual(registro["idioma"], "eng")
        self.assertEqual(registro["confianca_media"], 91.0)

    def test_pagina_que_falha_nao_derruba_as_outras(self):
        def motor(pdf, pagina, idioma):
            if pagina == 1:
                raise RuntimeError("imagem ilegível")
            return LeituraDoMotor("ok")

        avisos = avaliacao_ocr.gerar_candidatos({"falso": motor}, self.paginas, self.base)
        self.assertEqual(len(avisos), 1)
        self.assertTrue((self.base / "candidatos" / "falso" / "doc_p0002.txt").is_file())

    def test_programa_ausente_interrompe(self):
        def motor(pdf, pagina, idioma):
            raise ErroConfiguracao("`tesseract` não está instalado.")

        with self.assertRaises(ErroConfiguracao):
            avaliacao_ocr.gerar_candidatos({"falso": motor}, self.paginas, self.base)


class TestMotorComReserva(unittest.TestCase):
    def test_reserva_so_quando_a_pagina_sai_quase_vazia(self):
        chamadas = []

        def principal(pdf, pagina, idioma):
            chamadas.append("principal")
            return LeituraDoMotor("" if pagina == 1 else "texto suficiente na página")

        def reserva(pdf, pagina, idioma):
            chamadas.append("reserva")
            return LeituraDoMotor("lido pela reserva")

        motor = avaliacao_ocr.MotorComReserva(principal, reserva, minimo=10)
        self.assertEqual(motor(Path("x.pdf"), 2, "por").texto, "texto suficiente na página")
        self.assertEqual(motor(Path("x.pdf"), 1, "por").texto, "lido pela reserva")
        self.assertEqual(chamadas, ["principal", "principal", "reserva"])


class TestMotorKraken(unittest.TestCase):
    """O motor do Kraken com `pdftoppm` e `podman` simulados — sem container."""

    def setUp(self):
        self._temporario = tempfile.TemporaryDirectory()
        self.modelos = Path(self._temporario.name)
        self.config = ConfigKraken(modelo="modelo.mlmodel")
        (self.modelos / "modelo.mlmodel").write_bytes(b"x")

    def tearDown(self):
        self._temporario.cleanup()

    def _simular(self, texto_do_kraken=None, erro_do_podman=""):
        chamadas = []

        def falso(comando, **_):
            chamadas.append(comando)
            if comando[0] == "podman":
                if texto_do_kraken is None:
                    return subprocess.CompletedProcess(comando, 125, "", erro_do_podman)
                pasta = next(v.split(":")[0] for v in comando if v.endswith(":/trabalho:Z"))
                (Path(pasta) / "pagina.txt").write_text(texto_do_kraken, encoding="utf-8")
            return subprocess.CompletedProcess(comando, 0, "", "")

        return falso, chamadas

    def test_hifen_de_fim_de_linha_do_catmus_vira_hifen(self):
        falso, chamadas = self._simular("da educa¬\nção")
        with mock.patch.object(clientes_pdf.subprocess, "run", side_effect=falso):
            leitura = clientes_pdf.MotorKraken(self.config, self.modelos)(Path("doc.pdf"), 2, "por")
        self.assertEqual(leitura.texto, "da educa-\nção")
        podman = chamadas[1]
        self.assertIn("--pull=never", podman)
        self.assertIn("/modelos/modelo.mlmodel", podman)

    def test_modelo_ausente_explica_como_baixar(self):
        (self.modelos / "modelo.mlmodel").unlink()
        with self.assertRaises(ErroConfiguracao) as contexto:
            clientes_pdf.MotorKraken(self.config, self.modelos)(Path("doc.pdf"), 1, "por")
        self.assertIn("get 10.5281/zenodo.10592716", contexto.exception.sugestao)

    def test_imagem_ausente_explica_o_build(self):
        falso, _ = self._simular(erro_do_podman="Error: localhost/rag-kraken: image not known")
        with mock.patch.object(clientes_pdf.subprocess, "run", side_effect=falso):
            with self.assertRaises(ErroConfiguracao) as contexto:
                clientes_pdf.MotorKraken(self.config, self.modelos)(Path("doc.pdf"), 1, "por")
        self.assertIn("Containerfile.kraken", contexto.exception.sugestao)


class TestMotorPosicionado(unittest.TestCase):
    def test_mede_o_texto_derivado_das_regioes(self):
        motor = avaliacao_ocr.MotorPosicionado(ReconhecedorFalso(posicionado=True), ConfigRegioes())
        self.assertEqual(motor(Path("doc.pdf"), 2, "por").texto, "Texto reconhecido da página 2 com acentuação.")

    def test_regras_desligadas_deixam_o_carimbo(self):
        regioes = ConfigRegioes(marcar_carimbo=False)
        leitura = avaliacao_ocr.MotorPosicionado(ReconhecedorFalso(posicionado=True), regioes)(
            Path("doc.pdf"), 2, "por"
        )
        self.assertIn("INSTITUTO PAULO FREIRE", leitura.texto)


class TestConfiancaDoTsv(unittest.TestCase):
    def test_media_so_das_palavras_com_texto(self):
        tsv = (
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
            "2\t1\t1\t0\t0\t0\t0\t0\t10\t10\t-1\t\n"
            "5\t1\t1\t1\t1\t1\t0\t0\t5\t5\t90.0\tEducação\n"
            "5\t1\t1\t1\t1\t2\t0\t0\t5\t5\t70.0\tpopular\n"
            "5\t1\t1\t1\t1\t3\t0\t0\t5\t5\t95.0\t \n"
        )
        self.assertEqual(confianca_media_do_tsv(tsv), 80.0)

    def test_sem_palavras(self):
        self.assertIsNone(confianca_media_do_tsv("level\tconf\ttext\n"))


if __name__ == "__main__":
    unittest.main()
