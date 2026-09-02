"""
Recuperação léxica (BM25) e a fusão com a densa.

Está desligada por padrão porque o corpus atual é translíngue, que é o cenário em
que ela perde. Estes testes garantem que ela esteja correta quando o acervo do
IPF — de idioma casado e vocabulário técnico exato — tornar o cenário favorável.

O ponto que mais importa é o peso: com peso igual o léxico arrasta o denso para
baixo, e foi esse detalhe que fez a primeira medição concluir errado.
"""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from apoio import RecuperadorFalso

from rag.config import ConfigBusca  # noqa: E402
from rag.erros import ErroPreRequisito  # noqa: E402
from rag.lexico import IndiceLexico, RecuperadorHibrido, reescalar_para, tokenizar  # noqa: E402
from rag.modelos import TrechoRecuperado  # noqa: E402

CHUNKS = [
    {
        "chunk_id": "a::0",
        "texto": "the Hist are sentient trees of Black Marsh",
        "documento_origem": "a.txt",
        "titulo_pagina": "Lore:Hist",
        "chunk_index": 0,
    },
    {
        "chunk_id": "b::0",
        "texto": "Argonians are the reptilian natives of Black Marsh",
        "documento_origem": "b.txt",
        "titulo_pagina": "Lore:Argonian",
        "chunk_index": 0,
    },
    {
        "chunk_id": "c::0",
        "texto": "the Dwemer disappeared without explanation",
        "documento_origem": "c.txt",
        "titulo_pagina": "Lore:Dwemer",
        "chunk_index": 0,
    },
    {
        "chunk_id": "d::0",
        "texto": "Black Marsh is a swampland province",
        "documento_origem": "d.txt",
        "titulo_pagina": "Lore:Black Marsh",
        "chunk_index": 0,
    },
]


def indice_de_teste(chunks=None) -> tuple[IndiceLexico, TemporaryDirectory]:
    pasta = TemporaryDirectory()
    caminho = Path(pasta.name) / "chunks.jsonl"
    caminho.write_text("\n".join(json.dumps(c) for c in (chunks or CHUNKS)), encoding="utf-8")
    return IndiceLexico(caminho), pasta


def trecho(identificador: str, score: float = 0.9) -> TrechoRecuperado:
    return TrechoRecuperado(
        texto=f"texto {identificador}",
        titulo_pagina=f"Lore:{identificador}",
        documento_origem=f"{identificador}.txt",
        chunk_id=f"{identificador}::0",
        score=score,
    )


class TestTokenizacao(unittest.TestCase):
    def test_separa_e_normaliza(self):
        self.assertEqual(tokenizar("Os Hist, de Black-Marsh!"), ["os", "hist", "de", "black", "marsh"])

    def test_preserva_acentos_do_portugues(self):
        """O acervo do IPF é em português: perder acento perderia o termo."""
        self.assertIn("conscientização", tokenizar("a conscientização como práxis"))

    def test_descarta_token_de_uma_letra(self):
        self.assertEqual(tokenizar("a o e x"), [])

    def test_mantem_numero(self):
        self.assertIn("1968", tokenizar("o ano de 1968"))


class TestIndice(unittest.TestCase):
    def test_acha_pelo_termo_exato(self):
        indice, pasta = indice_de_teste()
        with pasta:
            achados = indice.buscar("Hist", k=1)
            self.assertEqual(achados[0].titulo_pagina, "Lore:Hist")

    def test_termo_raro_vence_termo_comum(self):
        """'Black Marsh' aparece em três chunks; 'Dwemer' em um. O IDF decide."""
        indice, pasta = indice_de_teste()
        with pasta:
            achados = indice.buscar("Dwemer Black Marsh", k=1)
            self.assertEqual(achados[0].titulo_pagina, "Lore:Dwemer")

    def test_termo_ausente_nao_devolve_nada(self):
        indice, pasta = indice_de_teste()
        with pasta:
            self.assertEqual(indice.buscar("Numidium", k=5), [])

    def test_respeita_o_k(self):
        indice, pasta = indice_de_teste()
        with pasta:
            self.assertEqual(len(indice.buscar("Black Marsh", k=2)), 2)

    def test_sem_arquivo_de_chunks_explica_o_que_falta(self):
        indice = IndiceLexico(Path("/nao/existe/chunks.jsonl"))
        with self.assertRaises(ErroPreRequisito) as capturado:
            indice.buscar("qualquer", k=1)
        self.assertIn("chunks.jsonl", capturado.exception.mensagem)
        self.assertIn("chunking", capturado.exception.sugestao)

    def test_a_ordem_e_estavel_entre_execucoes(self):
        indice, pasta = indice_de_teste()
        with pasta:
            primeira = [t.chunk_id for t in indice.buscar("Black Marsh", k=4)]
            self.assertEqual(primeira, [t.chunk_id for t in indice.buscar("Black Marsh", k=4)])


class TestHibrido(unittest.TestCase):
    def _hibrido(self, denso_devolve, **ajustes):
        indice, pasta = indice_de_teste()
        config = ConfigBusca(k=3, limiar_relativo=0.0, **ajustes)
        return RecuperadorHibrido(RecuperadorFalso(padrao=denso_devolve), indice, config), pasta

    def test_funde_os_dois_rankings(self):
        hibrido, pasta = self._hibrido([trecho("Dwemer")])
        with pasta:
            paginas = {t.titulo_pagina for t in hibrido.buscar("Hist", k=3)}
        self.assertIn("Lore:Dwemer", paginas, "o denso deveria estar na fusão")
        self.assertIn("Lore:Hist", paginas, "o léxico deveria estar na fusão")

    def test_o_denso_pesa_mais(self):
        """Com peso igual o léxico arrasta o denso para baixo — medido."""
        hibrido, pasta = self._hibrido([trecho("Dwemer")], peso_denso=5)
        with pasta:
            self.assertEqual(hibrido.buscar("Hist", k=3)[0].titulo_pagina, "Lore:Dwemer")

    def test_sem_chunks_a_busca_densa_segue_sozinha(self):
        """A recuperação não pode parar por causa de uma camada opcional."""
        config = ConfigBusca(k=2, limiar_relativo=0.0)
        hibrido = RecuperadorHibrido(
            RecuperadorFalso(padrao=[trecho("a"), trecho("b")]),
            IndiceLexico(Path("/nao/existe/chunks.jsonl")),
            config,
        )
        self.assertEqual(len(hibrido.buscar("qualquer")), 2)

    def test_respeita_o_k_pedido(self):
        hibrido, pasta = self._hibrido([trecho(c) for c in "xyz"])
        with pasta:
            self.assertEqual(len(hibrido.buscar("Black Marsh", k=2)), 2)

    def test_cumpre_o_protocolo(self):
        from rag.protocolos import RecuperadorDeTrechos

        hibrido, pasta = self._hibrido([])
        with pasta:
            self.assertIsInstance(hibrido, RecuperadorDeTrechos)


class TestEscalaDosScores(unittest.TestCase):
    """Cosseno e BM25 vivem em escalas diferentes, e misturá-las quebra o corte.

    `fundir_por_rrf` conserva o melhor score original de cada trecho, e a
    política de quantidade dinâmica corta por fração do score do primeiro
    colocado. Sem reescalar, um chunk achado só pelo léxico entrava com um número
    dez vezes maior e o corte descartava quase tudo — medido, `trechos/caso` caía
    de 8,9 para 6,5, e o recall de 92% para 85%.
    """

    def _lexicos(self, *scores):
        return [trecho(f"l{n}", score=s) for n, s in enumerate(scores)]

    def _densos(self, *scores):
        return [trecho(f"d{n}", score=s) for n, s in enumerate(scores)]

    def test_traz_para_a_faixa_dos_densos(self):
        reescalados = reescalar_para(self._lexicos(18.0, 9.0, 2.0), self._densos(0.70, 0.50))
        self.assertAlmostEqual(max(t.score for t in reescalados), 0.70)
        self.assertAlmostEqual(min(t.score for t in reescalados), 0.50)

    def test_preserva_a_ordem(self):
        reescalados = reescalar_para(self._lexicos(18.0, 9.0, 2.0), self._densos(0.70, 0.50))
        self.assertEqual([t.chunk_id for t in reescalados], ["l0::0", "l1::0", "l2::0"])
        self.assertGreater(reescalados[0].score, reescalados[1].score)

    def test_scores_iguais_nao_dividem_por_zero(self):
        reescalados = reescalar_para(self._lexicos(5.0, 5.0), self._densos(0.70, 0.50))
        self.assertEqual(len(reescalados), 2)

    def test_sem_densos_devolve_como_veio(self):
        originais = self._lexicos(18.0, 9.0)
        self.assertEqual([t.score for t in reescalar_para(originais, [])], [18.0, 9.0])

    def test_sem_lexicos_devolve_vazio(self):
        self.assertEqual(reescalar_para([], self._densos(0.7)), [])

    def test_nao_altera_o_resto_do_trecho(self):
        (reescalado,) = reescalar_para(self._lexicos(18.0), self._densos(0.7, 0.5))
        self.assertEqual(reescalado.chunk_id, "l0::0")
        self.assertEqual(reescalado.texto, "texto l0")


if __name__ == "__main__":
    unittest.main()
