"""Testes da extração do acervo — a etapa inteira com dublês, e o parsing dos clientes sem os binários."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from apoio import LeitorFalso, ReconhecedorFalso

from rag.clientes import pdf as clientes_pdf
from rag.config import Config, ConfigExtracao, ConfigKraken, ConfigRegioes
from rag.erros import ErroConfiguracao, ErroPipeline, ErroPreRequisito
from rag.etapas import extracao
from rag.servico import Servico
from rag.texto_posicionado import ler_page_xml

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


class TestTextoPosicionadoNaExtracao(unittest.TestCase):
    """Com um motor que dá coordenadas: PAGE XML por página e `.txt` derivado sem o carimbo."""

    def setUp(self):
        self._temporario = tempfile.TemporaryDirectory()
        raiz = Path(self._temporario.name)
        self.exportacao, self.saida = raiz / "exportacao", raiz / "texto"
        self.config = ConfigExtracao(minimo_de_caracteres_por_pagina=10)
        criar_item(self.exportacao, "item_000", "123/9", "misto.pdf\n", {"misto.pdf": b"misto"})
        self.leitor = LeitorFalso({"misto.pdf": ["", TEXTO_BOM, ""]})
        self.reconhecedor = ReconhecedorFalso(posicionado=True)
        self.paginas = self.saida / "123_9" / "misto.pdf.paginas"

    def tearDown(self):
        self._temporario.cleanup()

    def executar(self, **opcoes):
        return extracao.executar(self.config, self.exportacao, self.saida, self.leitor, self.reconhecedor, **opcoes)

    def test_grava_o_page_de_cada_pagina_do_ocr(self):
        resultado = self.executar()
        self.assertEqual(sorted(p.name for p in self.paginas.iterdir()), ["pagina_0001.ocr.xml", "pagina_0003.ocr.xml"])
        self.assertEqual(resultado.detalhes["paginas_posicionadas"], 2)
        self.assertEqual(
            ler_page_xml(self.paginas.joinpath("pagina_0001.ocr.xml").read_bytes()).contagem_por_tipo(),
            {"texto": 1, "carimbo": 2},
        )

    def test_o_txt_sai_das_regioes_sem_o_carimbo(self):
        self.executar()
        paginas = (self.saida / "123_9" / "misto.pdf.txt").read_text(encoding="utf-8").split("\f")
        self.assertEqual(
            paginas,
            [
                "Texto reconhecido da página 1 com acentuação.",
                TEXTO_BOM,
                "Texto reconhecido da página 3 com acentuação.",
            ],
        )

    def test_registro_traz_as_regioes_e_as_regras(self):
        self.executar(regioes=ConfigRegioes(zona_do_carimbo=0.2))
        registro = json.loads((self.saida / "123_9" / "misto.pdf.json").read_text(encoding="utf-8"))
        self.assertEqual(registro["paginas_posicionadas"], [1, 3])
        self.assertEqual(registro["linhas_por_tipo"], {"carimbo": 4, "texto": 2})
        self.assertEqual(registro["regras_de_regiao"]["zona_do_carimbo"], 0.2)

    def test_refazer_troca_o_page_do_ocr_e_preserva_o_revisado(self):
        self.executar()
        (self.paginas / "pagina_0009.ocr.xml").write_text("velho", encoding="utf-8")
        (self.paginas / "pagina_0001.revisada.xml").write_text("revisão", encoding="utf-8")
        self.executar(refazer=True)
        nomes = sorted(p.name for p in self.paginas.iterdir())
        self.assertEqual(nomes, ["pagina_0001.ocr.xml", "pagina_0001.revisada.xml", "pagina_0003.ocr.xml"])

    def test_motor_sem_coordenadas_nao_grava_page(self):
        self.reconhecedor.posicionado = False
        self.executar()
        self.assertFalse(self.paginas.exists())


class TestReconhecedorKraken(unittest.TestCase):
    """Lotes de páginas numa execução do container, com `pdftoppm` e `podman` simulados."""

    PAGE = (
        '<PcGts xmlns="http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15">'
        '<Page imageFilename="p.png" imageWidth="10" imageHeight="20"><TextRegion id="r" custom="type {{type:text;}}">'
        '<Coords points="0,0 9,19"/><TextLine id="l"><Coords points="0,0 9,5"/>'
        "<TextEquiv><Unicode>{}</Unicode></TextEquiv></TextLine></TextRegion></Page></PcGts>"
    )

    def setUp(self):
        self._temporario = tempfile.TemporaryDirectory()
        self.modelos = Path(self._temporario.name)
        (self.modelos / "m.mlmodel").write_bytes(b"x")
        self.config = ConfigKraken(modelo="m.mlmodel", paginas_por_chamada=2)

    def tearDown(self):
        self._temporario.cleanup()

    def _simular(self):
        chamadas = []

        def falso(comando, **_):
            if comando[0] == "podman":
                chamadas.append(comando)
                pasta = Path(next(v.split(":")[0] for v in comando if v.endswith(":/trabalho:Z")))
                saidas = [comando[i + 2] for i, v in enumerate(comando) if v == "-i"]
                for saida in saidas:
                    (pasta / saida).write_text(self.PAGE.format(saida), encoding="utf-8")
            return _processo()

        return falso, chamadas

    def test_manda_as_paginas_em_lotes_e_le_o_page(self):
        falso, chamadas = self._simular()
        with mock.patch.object(clientes_pdf.subprocess, "run", side_effect=falso):
            paginas = clientes_pdf.ReconhecedorKraken(self.config, self.modelos).reconhecer(Path("doc.pdf"), [1, 4, 7])
        self.assertEqual(len(chamadas), 2)
        self.assertIn("-x", chamadas[0])
        self.assertEqual(chamadas[0].count("-i"), 2)
        self.assertEqual(sorted(paginas), [1, 4, 7])
        self.assertEqual(paginas[4].regioes[0].linhas[0].texto, "pagina_0004.xml")
        self.assertTrue(paginas[7].tem_posicao)

    def test_modelo_ausente_falha_antes_de_rasterizar(self):
        (self.modelos / "m.mlmodel").unlink()
        with mock.patch.object(clientes_pdf.subprocess, "run") as rodar:
            with self.assertRaises(ErroConfiguracao):
                clientes_pdf.ReconhecedorKraken(self.config, self.modelos).reconhecer(Path("doc.pdf"), [1])
        rodar.assert_not_called()

    def test_saida_faltando_e_erro_do_documento(self):
        def sem_saida(comando, **_):
            return _processo()

        with mock.patch.object(clientes_pdf.subprocess, "run", side_effect=sem_saida):
            with self.assertRaises(ErroPipeline) as contexto:
                clientes_pdf.ReconhecedorKraken(self.config, self.modelos).reconhecer(Path("doc.pdf"), [3])
        self.assertNotIsInstance(contexto.exception, ErroConfiguracao)
        self.assertIn("páginas 3–3", str(contexto.exception))


class TestEscolhaDoMotor(unittest.TestCase):
    def test_kraken_e_o_padrao_e_ocrmypdf_continua_disponivel(self):
        self.assertIsInstance(Servico(Config()).reconhecedor, clientes_pdf.ReconhecedorKraken)
        config = Config(extracao=ConfigExtracao(motor="ocrmypdf"))
        self.assertIsInstance(Servico(config).reconhecedor, clientes_pdf.ReconhecedorOcrmypdf)

    def test_motor_desconhecido_explica_as_opcoes(self):
        with self.assertRaises(ErroConfiguracao) as contexto:
            _ = Servico(Config(extracao=ConfigExtracao(motor="tesseract"))).reconhecedor
        self.assertIn("kraken", contexto.exception.sugestao)


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
            textos = self.reconhecedor.reconhecer_texto(Path("doc.pdf"), [2, 4])
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
                self.reconhecedor.reconhecer_texto(Path("doc.pdf"), [1])

    def test_outra_falha_e_erro_do_documento(self):
        falso = self._rodar_com_sidecar("", returncode=7)
        with mock.patch.object(clientes_pdf.subprocess, "run", side_effect=falso):
            with self.assertRaises(ErroPipeline) as contexto:
                self.reconhecedor.reconhecer_texto(Path("doc.pdf"), [1])
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


TEXTO_ANTERIOR = "Txto anterlor da pagina escaneada, com erros."


def verificador_que_desconhece(*desconhecidas: str):
    """Dicionário de mentira: conhece tudo, menos as palavras dadas."""

    def verificar(palavras, idioma):
        return {p for p in palavras if p in desconhecidas}

    return verificar


class TestOcrAnterior(unittest.TestCase):
    """Texto sobre página escaneada é OCR de outro: vai ao nosso, e fica o de menos erro."""

    def setUp(self):
        self._temporario = tempfile.TemporaryDirectory()
        raiz = Path(self._temporario.name)
        self.exportacao, self.saida = raiz / "exportacao", raiz / "texto"
        self.config = ConfigExtracao(minimo_de_caracteres_por_pagina=10)
        criar_item(self.exportacao, "item_000", "123/9", "antigo.pdf\n", {"antigo.pdf": b"antigo"})
        # p. 1 e 2 escaneadas com camada de texto; p. 3 digital de verdade
        self.leitor = LeitorFalso(
            {"antigo.pdf": [TEXTO_ANTERIOR, TEXTO_ANTERIOR, TEXTO_BOM]},
            escaneadas={"antigo.pdf": {1, 2}},
            produtor="Producer: Paper Capture",
        )
        self.reconhecedor = ReconhecedorFalso()

    def tearDown(self):
        self._temporario.cleanup()

    def executar(self, verificador):
        extracao.executar(
            self.config, self.exportacao, self.saida, self.leitor, self.reconhecedor, verificador=verificador
        )
        pasta = self.saida / "123_9"
        registro = json.loads((pasta / "antigo.pdf.json").read_text(encoding="utf-8"))
        paginas = (pasta / "antigo.pdf.txt").read_text(encoding="utf-8").split("\f")
        return registro, paginas

    def test_so_as_escaneadas_vao_ao_ocr(self):
        self.executar(verificador_que_desconhece("Txto", "anterlor"))
        self.assertEqual(self.reconhecedor.pedidos, [("antigo.pdf", [1, 2])])

    def test_fica_o_nosso_quando_erra_menos(self):
        registro, paginas = self.executar(verificador_que_desconhece("Txto", "anterlor"))
        self.assertEqual(paginas[0], "Texto reconhecido da página 1 com acentuação.")
        self.assertEqual(paginas[2], TEXTO_BOM)
        self.assertEqual(registro["origem_por_pagina"], ["ocr", "ocr", "digital_nativo"])
        self.assertEqual(registro["comparacao_ocr_anterior"]["1"]["escolhido"], "ocr")
        self.assertEqual(registro["produtor_do_pdf"], "Producer: Paper Capture")
        anterior = self.saida / "123_9" / "antigo.pdf.paginas" / "pagina_0001.anterior.txt"
        self.assertEqual(anterior.read_text(encoding="utf-8"), TEXTO_ANTERIOR)

    def test_fica_o_anterior_quando_o_nosso_erra_mais(self):
        registro, paginas = self.executar(verificador_que_desconhece("reconhecido", "acentuação", "Texto"))
        self.assertEqual(paginas[0], TEXTO_ANTERIOR)
        self.assertEqual(registro["origem_por_pagina"], ["ocr_anterior", "ocr_anterior", "digital_nativo"])
        self.assertEqual(registro["origem_do_texto"], "ocr_anterior")
        self.assertNotIn("paginas_ocr", registro)

    def test_sem_dicionario_fica_o_nosso(self):
        registro, paginas = self.executar(lambda palavras, idioma: None)
        self.assertEqual(registro["origem_por_pagina"][:2], ["ocr", "ocr"])
        self.assertIsNone(registro["comparacao_ocr_anterior"]["2"]["anterior"])

    def test_nosso_vazio_nao_troca_texto_por_nada(self):
        self.reconhecedor = ReconhecedorFalso(ilegiveis={1, 2})
        registro, paginas = self.executar(None)
        self.assertEqual(paginas[:2], [TEXTO_ANTERIOR, TEXTO_ANTERIOR])
        self.assertEqual(registro["comparacao_ocr_anterior"]["1"]["escolhido"], "ocr_anterior")

    def test_pdf_todo_digital_nao_chama_o_ocr(self):
        self.leitor.escaneadas = {}
        registro, _ = self.executar(None)
        self.assertEqual(self.reconhecedor.pedidos, [])
        self.assertEqual(registro["origem_do_texto"], "digital_nativo")
        self.assertNotIn("origem_por_pagina", registro)


class TestCoberturaDeImagem(unittest.TestCase):
    """`pdfimages -list` → fração da página coberta pela maior imagem."""

    INFO = "Pages:           2\nPage    1 size: 480 x 672 pts\nPage    2 size: 595 x 842 pts (A4)\n"
    IMAGENS = (
        "page   num  type   width height color comp bpc  enc interp  object ID x-ppi y-ppi size ratio\n"
        "--------------------------------------------------------------------------------------------\n"
        "   1     0 image    1657  2341  gray    1   8  jpeg   no        61  0   200   200  347K 9.2%\n"
        "   1     1 stencil     1     1  -       1   1  image  no   [inline]   0.125 0.087    1B   - \n"
        "   2     2 image     780   573  icc     3   8  jpx    no         6  0   144   144  372K  28%\n"
    )

    def _rodar(self, comando, **_):
        return _processo(self.IMAGENS if comando[0] == "pdfimages" else self.INFO)

    def test_pagina_escaneada_e_foto_pequena(self):
        with mock.patch.object(clientes_pdf.subprocess, "run", side_effect=self._rodar):
            coberturas = clientes_pdf.LeitorPoppler().coberturas_de_imagem(Path("doc.pdf"))
        self.assertGreater(coberturas[0], 1.0)  # a imagem passa da margem
        self.assertAlmostEqual(coberturas[1], (780 / 2) * (573 / 2) / (595 * 842), places=3)

    def test_sem_pdfimages_nenhuma_pagina_e_escaneada(self):
        def rodar(comando, **_):
            return _processo(returncode=1) if comando[0] == "pdfimages" else _processo(self.INFO)

        with mock.patch.object(clientes_pdf.subprocess, "run", side_effect=rodar):
            self.assertEqual(clientes_pdf.LeitorPoppler().coberturas_de_imagem(Path("doc.pdf")), [0.0, 0.0])
