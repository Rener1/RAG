"""Texto posicionado: PAGE XML de ida e volta, texto derivado e regras de região."""

import unittest
from dataclasses import replace

from rag.config import ConfigRegioes
from rag.texto_posicionado import (
    TIPO_CARIMBO,
    TIPO_NUMERO_DE_PAGINA,
    TIPO_RUIDO,
    TIPO_TEXTO,
    Linha,
    PaginaPosicionada,
    Regiao,
    classificar_regioes,
    escrever_page_xml,
    ler_page_xml,
    marcar_ruido,
    semelhanca,
    separar_carimbo,
    texto_da_pagina,
    tipos_ignorados,
)

# Mesma forma do que o Kraken 7.1 escreve: tipo no `custom`, glifos dentro das
# palavras, confiança em cada nível e nenhuma ordem de leitura.
PAGE_DO_KRAKEN = """<?xml version="1.0" encoding="UTF-8"?>
<PcGts xmlns="http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15">
  <Metadata><Creator>kraken 7.1.1</Creator></Metadata>
  <Page imageFilename="pagina.png" imageWidth="1000" imageHeight="2000">
    <TextRegion id="r1" custom="type {type:text;}">
      <Coords points="100,100 900,100 900,300 100,300"/>
      <TextLine id="l1" custom="type {type:default;}">
        <Coords points="100,100 900,100 900,150 100,150"/>
        <Baseline points="100,140 900,140"/>
        <Word id="w1">
          <Coords points="100,100 300,100 300,150 100,150"/>
          <Glyph id="g1"><Coords points="100,100 120,150"/><TextEquiv conf="0.9"><Unicode>e</Unicode></TextEquiv></Glyph>
          <TextEquiv conf="0.97"><Unicode>educa¬</Unicode></TextEquiv>
        </Word>
        <TextEquiv conf="0.97"><Unicode>educa¬</Unicode></TextEquiv>
      </TextLine>
      <TextLine id="l2">
        <Coords points="100,160 900,160 900,210 100,210"/>
        <TextEquiv conf="0.99"><Unicode>ção do adulto</Unicode></TextEquiv>
      </TextLine>
    </TextRegion>
    <TextRegion id="r2" type="paragraph">
      <Coords points="100,400 900,400 900,500 100,500"/>
      <TextLine id="l3">
        <Coords points="100,400 900,400 900,450 100,450"/>
        <TextEquiv><Unicode>segundo bloco</Unicode></TextEquiv>
      </TextLine>
    </TextRegion>
  </Page>
</PcGts>
"""


def _linha(id_: str, texto: str, y: int) -> Linha:
    return Linha(id_, texto, contorno=((100, y), (900, y), (900, y + 40), (100, y + 40)))


def _pagina(*regioes: Regiao) -> PaginaPosicionada:
    return PaginaPosicionada(largura=1000, altura=2000, regioes=regioes)


CORPO = Regiao(
    "corpo",
    TIPO_TEXTO,
    contorno=((100, 1000), (900, 1000), (900, 1940), (100, 1940)),
    linhas=(
        _linha("c1", "O texto do documento continua aqui", 1000),
        _linha("c2", "e termina perto do rodapé.", 1750),
        _linha("c3", "INSTITUTO PAULO FREIRE", 1800),
        _linha("c4", "Rua Cerro Corá, 550 2.° andar cj. 22", 1850),
        _linha("c5", "E-mail: ipf(Opaulofreire.ore", 1900),
    ),
)


class TestLeituraDoPage(unittest.TestCase):
    def setUp(self) -> None:
        self.pagina = ler_page_xml(PAGE_DO_KRAKEN)

    def test_le_dimensoes_regioes_e_linhas(self) -> None:
        self.assertEqual((self.pagina.largura, self.pagina.altura, self.pagina.imagem), (1000, 2000, "pagina.png"))
        self.assertEqual([r.id for r in self.pagina.regioes], ["r1", "r2"])
        self.assertEqual([linha.texto for linha in self.pagina.regioes[0].linhas], ["educa¬", "ção do adulto"])

    def test_tipo_do_kraken_e_do_esquema_viram_texto(self) -> None:
        self.assertEqual({r.tipo for r in self.pagina.regioes}, {TIPO_TEXTO})

    def test_tipo_proprio_no_custom_e_mantido(self) -> None:
        pagina = ler_page_xml(PAGE_DO_KRAKEN.replace("type {type:text;}", "structure {type:legenda;}"))
        self.assertEqual(pagina.regioes[0].tipo, "legenda")

    def test_confianca_por_palavra_e_por_linha_sem_os_glifos(self) -> None:
        linha = self.pagina.regioes[0].linhas[0]
        self.assertEqual(linha.confianca, 0.97)
        self.assertEqual([(p.texto, p.confianca) for p in linha.palavras], [("educa¬", 0.97)])
        self.assertEqual(linha.linha_de_base, ((100, 140), (900, 140)))

    def test_palavra_que_e_so_espaco_e_descartada(self) -> None:
        espaco = '<Word id="w9"><Coords points="300,100 310,150"/><TextEquiv conf="1.0"><Unicode> </Unicode></TextEquiv></Word>'
        pagina = ler_page_xml(PAGE_DO_KRAKEN.replace("</Word>", "</Word>" + espaco, 1))
        self.assertEqual([p.texto for p in pagina.regioes[0].linhas[0].palavras], ["educa¬"])

    def test_linha_sem_confianca_fica_none(self) -> None:
        self.assertIsNone(self.pagina.regioes[1].linhas[0].confianca)

    def test_ordem_de_leitura_explicita_manda(self) -> None:
        ordem = (
            '<ReadingOrder><OrderedGroup id="o"><RegionRefIndexed index="0" regionRef="r2"/>'
            '<RegionRefIndexed index="1" regionRef="r1"/></OrderedGroup></ReadingOrder>'
        )
        pagina = ler_page_xml(PAGE_DO_KRAKEN.replace('imageHeight="2000">', f'imageHeight="2000">{ordem}'))
        self.assertEqual([r.id for r in pagina.regioes], ["r2", "r1"])

    def test_sem_page_levanta_erro(self) -> None:
        with self.assertRaises(ValueError):
            ler_page_xml('<PcGts xmlns="http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15"/>')


class TestEscritaDoPage(unittest.TestCase):
    def test_ida_e_volta_preserva_a_pagina(self) -> None:
        pagina = classificar_regioes(_pagina(CORPO), ConfigRegioes())
        self.assertEqual(ler_page_xml(escrever_page_xml(pagina)), replace(pagina, imagem="pagina.png"))

    def test_regiao_sem_contorno_ganha_o_retangulo_das_linhas(self) -> None:
        sem_contorno = replace(CORPO, contorno=())
        self.assertEqual(ler_page_xml(escrever_page_xml(_pagina(sem_contorno))).regioes[0].contorno, CORPO.contorno)

    def test_ida_e_volta_do_que_o_kraken_escreveu(self) -> None:
        pagina = ler_page_xml(PAGE_DO_KRAKEN)
        self.assertEqual(ler_page_xml(escrever_page_xml(pagina)), pagina)

    def test_declara_onde_esta_o_esquema(self) -> None:
        """O eScriptorium recusa PAGE sem `xsi:schemaLocation`."""
        xml = escrever_page_xml(_pagina(CORPO))
        self.assertIn('xsi:schemaLocation="http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15 ', xml)
        self.assertIn("2019-07-15/pagecontent.xsd", xml)

    def test_escreve_a_ordem_de_leitura_e_o_tipo_no_custom(self) -> None:
        xml = escrever_page_xml(_pagina(Regiao("b", TIPO_CARIMBO), Regiao("a", TIPO_TEXTO)))
        self.assertLess(xml.index('regionRef="b"'), xml.index('regionRef="a"'))
        self.assertIn('custom="structure {type:carimbo;}"', xml)
        self.assertEqual([r.id for r in ler_page_xml(xml).regioes], ["b", "a"])


class TestTextoDaPagina(unittest.TestCase):
    def test_uma_linha_em_branco_entre_regioes_e_hifen_de_fim_de_linha(self) -> None:
        self.assertEqual(texto_da_pagina(ler_page_xml(PAGE_DO_KRAKEN)), "educa-\nção do adulto\n\nsegundo bloco")

    def test_pula_os_tipos_ignorados(self) -> None:
        pagina = _pagina(
            Regiao("t", TIPO_TEXTO, linhas=(_linha("1", "conteúdo", 100),)),
            Regiao("c", TIPO_CARIMBO, linhas=(_linha("2", "INSTITUTO PAULO FREIRE", 1900),)),
            Regiao("r", TIPO_RUIDO, linhas=(_linha("3", "E", 200),)),
        )
        self.assertEqual(texto_da_pagina(pagina), "conteúdo")
        self.assertIn("INSTITUTO", texto_da_pagina(pagina, ignorar=frozenset()))

    def test_tipos_ignorados_saem_da_configuracao(self) -> None:
        self.assertEqual(tipos_ignorados(ConfigRegioes(tipos_ignorados="carimbo | ruido|")), {"carimbo", "ruido"})


class TestCarimbo(unittest.TestCase):
    def test_semelhanca_ignora_caixa_acento_e_pontuacao(self) -> None:
        self.assertEqual(semelhanca("Rua Cerro Corá, 550", "rua cerro cora 550"), 1.0)
        self.assertGreater(semelhanca("E-mail: ipf(Opaulofreire.ore", "E-mail: ipf@paulofreire.org"), 0.6)

    def test_separa_as_linhas_do_carimbo_numa_regiao_propria(self) -> None:
        pagina = separar_carimbo(_pagina(CORPO), ConfigRegioes())
        self.assertEqual([r.tipo for r in pagina.regioes], [TIPO_TEXTO, TIPO_CARIMBO])
        self.assertEqual([linha.id for linha in pagina.regioes[0].linhas], ["c1", "c2"])
        self.assertEqual([linha.id for linha in pagina.regioes[1].linhas], ["c3", "c4", "c5"])
        self.assertEqual(pagina.regioes[1].contorno, ((100, 1800), (900, 1800), (900, 1940), (100, 1940)))

    def test_carimbo_fora_do_rodape_fica(self) -> None:
        alto = Regiao(
            "a",
            TIPO_TEXTO,
            linhas=(_linha("1", "INSTITUTO PAULO FREIRE", 300), _linha("2", "Rua Cerro Corá, 550", 350)),
        )
        self.assertEqual(separar_carimbo(_pagina(alto), ConfigRegioes()), _pagina(alto))

    def test_uma_linha_parecida_sozinha_e_coincidencia(self) -> None:
        carta = Regiao(
            "a",
            TIPO_TEXTO,
            linhas=(_linha("1", "Prezados, escrevo ao", 1750), _linha("2", "Instituto Paulo Freire", 1800)),
        )
        self.assertEqual(separar_carimbo(_pagina(carta), ConfigRegioes()), _pagina(carta))

    def test_regiao_toda_de_carimbo_e_trocada_e_nao_duplicada(self) -> None:
        so_carimbo = Regiao("a", TIPO_TEXTO, linhas=CORPO.linhas[2:])
        pagina = separar_carimbo(_pagina(so_carimbo), ConfigRegioes())
        self.assertEqual([(r.id, r.tipo) for r in pagina.regioes], [("a_carimbo", TIPO_CARIMBO)])

    def test_desligado_ou_sem_carimbo_conhecido_nao_mexe(self) -> None:
        self.assertEqual(separar_carimbo(_pagina(CORPO), ConfigRegioes(marcar_carimbo=False)), _pagina(CORPO))
        self.assertEqual(separar_carimbo(_pagina(CORPO), ConfigRegioes(carimbos="")), _pagina(CORPO))

    def test_regiao_ja_tipada_pela_revisao_nao_e_tocada(self) -> None:
        legenda = replace(CORPO, tipo="legenda")
        self.assertEqual(separar_carimbo(_pagina(legenda), ConfigRegioes()), _pagina(legenda))


class TestRuido(unittest.TestCase):
    MARGEM = Regiao(
        "m", TIPO_TEXTO, linhas=tuple(_linha(str(i), t, 100 * i) for i, t in enumerate(["E", "3", "—", "n 22", "D2"]))
    )

    def test_regiao_so_de_fragmentos_vira_ruido(self) -> None:
        self.assertEqual(marcar_ruido(_pagina(self.MARGEM), ConfigRegioes()).regioes[0].tipo, TIPO_RUIDO)

    def test_numero_de_pagina_e_marcado_a_parte(self) -> None:
        numero = Regiao("n", TIPO_TEXTO, linhas=(_linha("1", "-2-", 50),))
        self.assertEqual(marcar_ruido(_pagina(numero), ConfigRegioes()).regioes[0].tipo, TIPO_NUMERO_DE_PAGINA)

    def test_regiao_com_uma_palavra_de_verdade_continua_texto(self) -> None:
        mista = replace(self.MARGEM, linhas=(*self.MARGEM.linhas, _linha("x", "adulto", 900)))
        self.assertEqual(marcar_ruido(_pagina(mista), ConfigRegioes()).regioes[0].tipo, TIPO_TEXTO)

    def test_duas_linhas_curtas_nao_bastam(self) -> None:
        curta = replace(self.MARGEM, linhas=self.MARGEM.linhas[:2])
        self.assertEqual(marcar_ruido(_pagina(curta), ConfigRegioes()).regioes[0].tipo, TIPO_TEXTO)

    def test_desligado_nao_mexe(self) -> None:
        self.assertEqual(marcar_ruido(_pagina(self.MARGEM), ConfigRegioes(marcar_ruido=False)), _pagina(self.MARGEM))

    def test_fragmento_na_margem_sai_da_regiao_do_corpo(self) -> None:
        def em(id_: str, texto: str, x0: int, x1: int) -> Linha:
            return Linha(id_, texto, contorno=((x0, 500), (x1, 500), (x1, 540), (x0, 540)))

        corpo = Regiao(
            "c",
            TIPO_TEXTO,
            linhas=(
                em("f1", "E", 10, 60),  # furo à esquerda
                em("t1", "Os Círculos de Pais e Professores", 100, 900),
                em("a1", "Pu4", 300, 600),  # fragmento fora da margem: anotação, fica
                em("f2", "3", 950, 990),  # furo à direita
                em("n1", "12", 10, 50),  # dígitos soltos na margem também são furo
            ),
        )
        pagina = marcar_ruido(_pagina(corpo), ConfigRegioes())
        self.assertEqual(
            [(r.tipo, [linha.id for linha in r.linhas]) for r in pagina.regioes],
            [(TIPO_TEXTO, ["t1", "a1"]), (TIPO_RUIDO, ["f1", "f2", "n1"])],
        )

    def test_classificar_aplica_as_duas_regras(self) -> None:
        pagina = classificar_regioes(_pagina(self.MARGEM, CORPO), ConfigRegioes())
        self.assertEqual([r.tipo for r in pagina.regioes], [TIPO_RUIDO, TIPO_TEXTO, TIPO_CARIMBO])
        self.assertEqual(pagina.contagem_por_tipo(), {TIPO_RUIDO: 5, TIPO_TEXTO: 2, TIPO_CARIMBO: 3})


if __name__ == "__main__":
    unittest.main()
