"""Testes da extração do acervo — a etapa inteira com dublês, e o parsing dos clientes sem os binários."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from apoio import LeitorFalso, ReconhecedorFalso

from rag.clientes import pdf as clientes_pdf
from rag.config import ConfigExtracao
from rag.erros import ErroConfiguracao, ErroPipeline, ErroPreRequisito
from rag.etapas import extracao

TEXTO_BOM = "Página com camada de texto digital, longa o bastante."


def criar_item(raiz: Path, pasta: str, handle: str | None, contents: str, arquivos: dict[str, bytes]) -> Path:
    """Uma pasta de item no formato de exportação do DSpace."""
    item = raiz / pasta
    item.mkdir(parents=True)
    (item / "contents").write_text(contents, encoding="utf-8")
    if handle is not None:
        (item / "handle").write_text(handle + "\n", encoding="utf-8")
    for nome, conteudo in arquivos.items():
        (item / nome).write_bytes(conteudo)
    return item


class TestFuncoesPuras(unittest.TestCase):
    def test_nome_seguro_troca_a_barra_do_handle(self):
        self.assertEqual(extracao.nome_seguro("123456789/42"), "123456789_42")

    def test_pagina_tem_texto_conta_so_letras_e_digitos(self):
        """Número de página solto e pontuação não fazem a página parecer ter texto."""
        self.assertFalse(extracao.pagina_tem_texto("  - 12 -  ....  ", 10))
        self.assertTrue(extracao.pagina_tem_texto("educação popular", 10))

    def test_normalizar_tira_form_feed_interno(self):
        """Um `\\f` dentro da página deslocaria a numeração de todas as seguintes."""
        self.assertNotIn("\f", extracao.normalizar_pagina("antes\fdepois"))

    def test_normalizar_compoe_acentos(self):
        decomposto = "educação"
        self.assertEqual(extracao.normalizar_pagina(decomposto), "educação")


class TestListarPdfs(unittest.TestCase):
    def setUp(self):
        self._temporario = tempfile.TemporaryDirectory()
        self.raiz = Path(self._temporario.name)

    def tearDown(self):
        self._temporario.cleanup()

    def test_pega_so_o_bundle_original(self):
        contents = (
            "carta.pdf\tbundle:ORIGINAL\tprimary:true\n"
            "carta.pdf.txt\tbundle:TEXT\n"
            "carta.pdf.jpg\tbundle:THUMBNAIL\n"
            "license.txt\tbundle:LICENSE\n"
            "anexo.pdf\n"
        )
        arquivos = {n: b"x" for n in ("carta.pdf", "carta.pdf.txt", "carta.pdf.jpg", "license.txt", "anexo.pdf")}
        criar_item(self.raiz, "item_000", "123/1", contents, arquivos)

        pdfs, avisos = extracao.listar_pdfs(self.raiz)

        self.assertEqual([p.arquivo for p in pdfs], ["carta.pdf", "anexo.pdf"])
        self.assertTrue(all(p.handle == "123/1" for p in pdfs))
        self.assertEqual(avisos, [])

    def test_item_sem_handle_usa_o_nome_da_pasta_e_avisa(self):
        criar_item(self.raiz, "item_007", None, "doc.pdf\n", {"doc.pdf": b"x"})
        pdfs, avisos = extracao.listar_pdfs(self.raiz)
        self.assertEqual(pdfs[0].handle, "item_007")
        self.assertEqual(len(avisos), 1)

    def test_pasta_sem_contents_e_arquivo_ausente_viram_aviso(self):
        (self.raiz / "lixo").mkdir()
        criar_item(self.raiz, "item_001", "123/2", "sumiu.pdf\n", {})
        pdfs, avisos = extracao.listar_pdfs(self.raiz)
        self.assertEqual(pdfs, [])
        self.assertEqual(len(avisos), 2)

    def test_nome_com_caminho_e_descartado(self):
        """O arquivo tem de estar na própria pasta do item — nada de `../`."""
        criar_item(self.raiz, "item_002", "123/3", "../fora.pdf\nsub/dentro.pdf\n", {})
        pdfs, _ = extracao.listar_pdfs(self.raiz)
        self.assertEqual(pdfs, [])


class TestEtapaDeExtracao(unittest.TestCase):
    """A etapa inteira, com leitor e OCR injetados — sem Poppler nem Tesseract."""

    def setUp(self):
        self._temporario = tempfile.TemporaryDirectory()
        raiz = Path(self._temporario.name)
        self.exportacao = raiz / "exportacao"
        self.saida = raiz / "texto"
        self.config = ConfigExtracao(minimo_de_caracteres_por_pagina=10)

        criar_item(self.exportacao, "item_000", "123/1", "nativo.pdf\n", {"nativo.pdf": b"nativo"})
        criar_item(self.exportacao, "item_001", "123/2", "misto.pdf\n", {"misto.pdf": b"misto"})
        criar_item(self.exportacao, "item_002", "123/3", "imagem.pdf\n", {"imagem.pdf": b"imagem"})

        self.leitor = LeitorFalso(
            {
                "nativo.pdf": [TEXTO_BOM, TEXTO_BOM],
                "misto.pdf": ["", TEXTO_BOM, " 3 "],
                "imagem.pdf": ["", ""],
            }
        )
        self.reconhecedor = ReconhecedorFalso()

    def tearDown(self):
        self._temporario.cleanup()

    def executar(self, **opcoes):
        return extracao.executar(self.config, self.exportacao, self.saida, self.leitor, self.reconhecedor, **opcoes)

    def registro(self, handle: str, arquivo: str) -> dict:
        caminho = self.saida / extracao.nome_seguro(handle) / f"{arquivo}.json"
        return json.loads(caminho.read_text(encoding="utf-8"))

    def texto(self, handle: str, arquivo: str) -> str:
        return (self.saida / extracao.nome_seguro(handle) / f"{arquivo}.txt").read_text(encoding="utf-8")

    def test_so_as_paginas_sem_texto_vao_ao_ocr(self):
        self.executar()
        self.assertEqual(
            sorted(self.reconhecedor.pedidos),
            [("imagem.pdf", [1, 2]), ("misto.pdf", [1, 3])],
        )

    def test_paginas_ficam_na_ordem_separadas_por_form_feed(self):
        self.executar()
        paginas = self.texto("123/2", "misto.pdf").split("\f")
        self.assertEqual(len(paginas), 3)
        self.assertIn("página 1", paginas[0])
        self.assertEqual(paginas[1], TEXTO_BOM)
        self.assertIn("página 3", paginas[2])

    def test_origem_do_texto_por_documento(self):
        self.executar()
        nativo = self.registro("123/1", "nativo.pdf")
        misto = self.registro("123/2", "misto.pdf")
        imagem = self.registro("123/3", "imagem.pdf")

        self.assertEqual(nativo["origem_do_texto"], "digital_nativo")
        self.assertNotIn("ocr_ferramenta", nativo)
        self.assertEqual(misto["origem_do_texto"], "ocr")
        self.assertEqual(misto["paginas_ocr"], [1, 3])
        self.assertEqual(imagem["ocr_ferramenta"], "ocr-falso")
        self.assertEqual(imagem["ocr_versao"], "0.0")
        self.assertEqual(imagem["total_de_paginas"], 2)

    def test_contagens_no_resultado(self):
        resultado = self.executar()
        self.assertEqual(resultado.processados, 3)
        self.assertEqual(resultado.detalhes["digital_nativo"], 1)
        self.assertEqual(resultado.detalhes["ocr"], 2)
        self.assertEqual(resultado.detalhes["paginas_ocr"], 4)

    def test_ocr_pior_que_a_camada_digital_e_descartado(self):
        """Página digital curta (folha de rosto) vai ao OCR, mas não troca texto exato por pior."""
        self.leitor.paginas_por_arquivo["nativo.pdf"] = ["Capítulo 3", TEXTO_BOM]
        self.reconhecedor.ilegiveis = {1}
        self.executar()

        registro = self.registro("123/1", "nativo.pdf")
        self.assertEqual(self.reconhecedor.pedidos[0], ("nativo.pdf", [1]))
        self.assertEqual(registro["origem_do_texto"], "digital_nativo")
        self.assertNotIn("paginas_ocr", registro)
        self.assertEqual(self.texto("123/1", "nativo.pdf").split("\f")[0], "Capítulo 3")

    def test_pagina_ilegivel_fica_marcada_para_revisao(self):
        self.reconhecedor.ilegiveis = {2}
        resultado = self.executar()
        self.assertEqual(self.registro("123/3", "imagem.pdf")["paginas_abaixo_do_minimo"], [2])
        self.assertEqual(resultado.detalhes["paginas_abaixo_do_minimo"], 1)

    def test_repetir_pula_o_que_ja_foi_extraido(self):
        self.executar()
        self.reconhecedor.pedidos.clear()

        resultado = self.executar()

        self.assertEqual(resultado.processados, 0)
        self.assertEqual(resultado.ignorados, 3)
        self.assertEqual(self.reconhecedor.pedidos, [])

    def test_original_alterado_e_refeito(self):
        self.executar()
        (self.exportacao / "item_000" / "nativo.pdf").write_bytes(b"outra versao")
        resultado = self.executar()
        self.assertEqual(resultado.processados, 1)
        self.assertEqual(resultado.ignorados, 2)

    def test_refazer_ignora_a_retomada(self):
        self.executar()
        self.assertEqual(self.executar(refazer=True).processados, 3)

    def test_documentos_restringe_e_refaz(self):
        self.executar()
        self.reconhecedor.pedidos.clear()

        resultado = self.executar(documentos=["123/3", "999/9"])

        self.assertEqual(resultado.processados, 1)
        self.assertEqual(self.reconhecedor.pedidos, [("imagem.pdf", [1, 2])])
        self.assertIn("handle 999/9 não está na exportação", resultado.detalhes["avisos"])

    def test_pdf_que_falha_nao_derruba_os_outros(self):
        del self.leitor.paginas_por_arquivo["misto.pdf"]
        resultado = self.executar()
        self.assertEqual(resultado.processados, 2)
        self.assertEqual(len(resultado.falhas), 1)
        self.assertIn("123/2", resultado.falhas[0])

    def test_ocr_ausente_interrompe_em_vez_de_falhar_documento_por_documento(self):
        def sem_ocr(caminho, paginas):
            raise ErroConfiguracao("`ocrmypdf` não está instalado.")

        self.reconhecedor.reconhecer = sem_ocr
        with self.assertRaises(ErroConfiguracao):
            self.executar()

    def test_registro_nunca_fica_sem_o_texto(self):
        """O `.json` marca o documento como pronto: sem `.txt` ao lado, a retomada mentiria."""
        with mock.patch.object(extracao, "_gravar_atomico", side_effect=OSError("disco cheio")):
            resultado = self.executar()
        self.assertEqual(len(resultado.falhas), 3)
        self.assertEqual(list(self.saida.glob("*/*.json")), [])

    def test_exportacao_ausente_e_pre_requisito(self):
        with self.assertRaises(ErroPreRequisito):
            extracao.executar(self.config, self.saida / "nada", self.saida, self.leitor, self.reconhecedor)

    def test_exportacao_sem_pdf_e_pre_requisito(self):
        vazia = self.saida / "vazia"
        vazia.mkdir(parents=True)
        with self.assertRaises(ErroPreRequisito):
            extracao.executar(self.config, vazia, self.saida, self.leitor, self.reconhecedor)


def _processo(stdout: str = "", returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


class TestLeitorPoppler(unittest.TestCase):
    """O parsing da saída do Poppler, com `subprocess.run` substituído."""

    def _ler(self, paginas_informadas: int, saida_do_pdftotext: str) -> list[str]:
        respostas = [_processo(f"Title: x\nPages:          {paginas_informadas}\n"), _processo(saida_do_pdftotext)]
        with mock.patch.object(clientes_pdf.subprocess, "run", side_effect=respostas):
            return clientes_pdf.LeitorPoppler().textos_das_paginas(Path("doc.pdf"))

    def test_descarta_o_pedaco_vazio_depois_do_ultimo_form_feed(self):
        self.assertEqual(self._ler(2, "um\fdois\f"), ["um", "dois"])

    def test_pagina_vazia_continua_contando(self):
        self.assertEqual(self._ler(3, "um\f\ftres\f"), ["um", "", "tres"])

    def test_contagem_divergente_e_erro(self):
        """Gravar com uma página a menos deslocaria a citação de todas as seguintes."""
        with self.assertRaises(ErroPipeline):
            self._ler(3, "um\fdois\f")

    def test_binario_ausente_explica_a_instalacao(self):
        with mock.patch.object(clientes_pdf.subprocess, "run", side_effect=FileNotFoundError):
            with self.assertRaises(ErroConfiguracao) as contexto:
                clientes_pdf.LeitorPoppler().textos_das_paginas(Path("doc.pdf"))
        self.assertIn("dnf install", contexto.exception.sugestao)


class TestReconhecedorOcrmypdf(unittest.TestCase):
    def setUp(self):
        self.reconhecedor = clientes_pdf.ReconhecedorOcrmypdf(ConfigExtracao(processos=2))

    def _rodar_com_sidecar(self, texto: str, returncode: int = 0):
        def falso(comando, **_):
            sidecar = Path(comando[comando.index("--sidecar") + 1])
            sidecar.write_text(texto, encoding="utf-8")
            falso.comando = comando
            return _processo(returncode=returncode, stderr="algo deu errado")

        return falso

    def test_devolve_so_as_paginas_pedidas(self):
        falso = self._rodar_com_sidecar("[OCR skipped on page 1]\fsegunda\f[OCR skipped on page 3]\fquarta")
        with mock.patch.object(clientes_pdf.subprocess, "run", side_effect=falso):
            textos = self.reconhecedor.reconhecer(Path("doc.pdf"), [2, 4])
        self.assertEqual(textos, {2: "segunda", 4: "quarta"})
        self.assertIn("2,4", falso.comando)
        self.assertEqual(falso.comando[falso.comando.index("--jobs") + 1], "2")

    def test_paginas_puladas_em_sequencia_nao_deslocam_a_numeracao(self):
        """O OCRmyPDF 16.7 junta páginas puladas seguidas num aviso só — conferido."""
        sidecar = "primeira\f[OCR skipped on page(s) 2-3]\fquarta\f[OCR skipped on page(s) 5]"
        self.assertEqual(clientes_pdf.paginas_do_sidecar(sidecar, [1, 4], "doc.pdf"), {1: "primeira", 4: "quarta"})

    def test_aviso_no_formato_antigo_tambem_serve(self):
        sidecar = "[OCR skipped on page 1]\fsegunda"
        self.assertEqual(clientes_pdf.paginas_do_sidecar(sidecar, [2], "doc.pdf"), {2: "segunda"})

    def test_aviso_fora_de_compasso_e_erro(self):
        """Melhor falhar o documento que gravar texto na página errada."""
        with self.assertRaises(ErroPipeline):
            clientes_pdf.paginas_do_sidecar("primeira\f[OCR skipped on page(s) 3]\fquarta", [1, 4], "doc.pdf")

    def test_pagina_pedida_que_nao_voltou_e_erro(self):
        with self.assertRaises(ErroPipeline):
            clientes_pdf.paginas_do_sidecar("primeira", [1, 2], "doc.pdf")

    def test_dependencia_ausente_interrompe(self):
        falso = self._rodar_com_sidecar("", returncode=clientes_pdf.SAIDA_DEPENDENCIA_AUSENTE)
        with mock.patch.object(clientes_pdf.subprocess, "run", side_effect=falso):
            with self.assertRaises(ErroConfiguracao):
                self.reconhecedor.reconhecer(Path("doc.pdf"), [1])

    def test_outra_falha_e_erro_do_documento(self):
        falso = self._rodar_com_sidecar("", returncode=7)
        with mock.patch.object(clientes_pdf.subprocess, "run", side_effect=falso):
            with self.assertRaises(ErroPipeline) as contexto:
                self.reconhecedor.reconhecer(Path("doc.pdf"), [1])
        self.assertNotIsInstance(contexto.exception, ErroConfiguracao)

    def test_identificacao_traz_as_duas_versoes(self):
        respostas = [_processo("16.13.0\n"), _processo("tesseract 5.5.3\n leptonica-1.85.0\n")]
        with mock.patch.object(clientes_pdf.subprocess, "run", side_effect=respostas):
            identificacao = self.reconhecedor.identificacao
        self.assertEqual(identificacao["versao"], "ocrmypdf 16.13.0; tesseract 5.5.3")
        self.assertIn("-l por", identificacao["parametros"])


if __name__ == "__main__":
    unittest.main()


class TestIdiomaDoCatalogo(unittest.TestCase):
    def test_mapeia_o_iso_do_dspace(self):
        self.assertEqual(extracao.idioma_do_tesseract("pt"), "por")
        self.assertEqual(extracao.idioma_do_tesseract("en_US"), "eng")
        self.assertEqual(extracao.idioma_do_tesseract("es"), "spa")
        self.assertEqual(extracao.idioma_do_tesseract("other"), "")

    def test_le_do_dublin_core_do_item(self):
        with tempfile.TemporaryDirectory() as pasta:
            item = criar_item(Path(pasta), "item", "123/9", "doc.pdf\n", {"doc.pdf": b"x"})
            (item / "dublin_core.xml").write_text(
                '<dublin_core><dcvalue element="language" qualifier="iso">fr</dcvalue></dublin_core>',
                encoding="utf-8",
            )
            pdfs, _ = extracao.listar_pdfs(Path(pasta))
        self.assertEqual(pdfs[0].idioma, "fra")

    def test_sem_dublin_core_fica_vazio(self):
        with tempfile.TemporaryDirectory() as pasta:
            criar_item(Path(pasta), "item", "123/9", "doc.pdf\n", {"doc.pdf": b"x"})
            pdfs, _ = extracao.listar_pdfs(Path(pasta))
        self.assertEqual(pdfs[0].idioma, "")
