"""
As estruturas de domínio, e o contrato de serialização do `Chunk`.

`como_dicionario` é o formato do `chunks.jsonl` e do payload do banco vetorial
ao mesmo tempo. Mudá-lo sem cuidado custa horas: o corpus atual tem 69285 chunks
indexados, e reindexar é a operação mais cara do pipeline. Por isso os campos de
proveniência acrescentados depois só são gravados quando têm valor — os testes
abaixo são o que garante que essa regra não se perca.
"""

import json
import unittest

from apoio import *  # noqa: F401,F403  — põe src/ no sys.path

from rag.modelos import Chunk, EstadoDaSessao, Sessao  # noqa: E402

# O formato anterior aos campos de proveniência — uma linha real do JSONL.
DICIONARIO_ANTIGO = {
    "chunk_id": "Lore_Argonian.txt::3",
    "texto": "The Argonians were given life by the Hist.",
    "documento_origem": "Lore_Argonian.txt",
    "titulo_pagina": "Lore:Argonian",
    "chunk_index": 3,
}


class TestSerializacaoDoChunk(unittest.TestCase):
    def test_chunk_sem_proveniencia_serializa_no_formato_antigo(self):
        """Regressão do sha256 do chunks.jsonl: sem isto, reindexar vira obrigatório."""
        chunk = Chunk(**DICIONARIO_ANTIGO)
        self.assertEqual(chunk.como_dicionario(), DICIONARIO_ANTIGO)

    def test_a_ordem_das_chaves_e_estavel(self):
        """O JSONL é comparado por hash; ordem diferente é arquivo diferente."""
        esperado = json.dumps(DICIONARIO_ANTIGO, ensure_ascii=False)
        self.assertEqual(json.dumps(Chunk(**DICIONARIO_ANTIGO).como_dicionario(), ensure_ascii=False), esperado)

    def test_dicionario_antigo_carrega_com_os_campos_novos_vazios(self):
        chunk = Chunk.de_dicionario(DICIONARIO_ANTIGO)
        self.assertEqual(chunk.pagina, 0)
        self.assertEqual(chunk.secao, "")
        self.assertEqual(chunk.versao_embedding, "")
        self.assertEqual(chunk.restricao_uso, "")

    def test_proveniencia_preenchida_e_gravada_e_relida(self):
        chunk = Chunk(
            **DICIONARIO_ANTIGO,
            pagina=12,
            secao="Mythology › Altmer",
            inicio=340,
            fim=1180,
            versao_embedding="bge-m3",
            restricao_uso="interno",
        )
        self.assertEqual(Chunk.de_dicionario(chunk.como_dicionario()), chunk)

    def test_campo_em_branco_nao_entra_no_payload(self):
        chunk = Chunk(**DICIONARIO_ANTIGO, secao="Mythology")
        dados = chunk.como_dicionario()
        self.assertIn("secao", dados)
        self.assertNotIn("pagina", dados)
        self.assertNotIn("restricao_uso", dados)

    def test_ida_e_volta_pelo_json(self):
        chunk = Chunk(**DICIONARIO_ANTIGO, pagina=7)
        self.assertEqual(Chunk.de_dicionario(json.loads(json.dumps(chunk.como_dicionario()))), chunk)


class TestSessao(unittest.TestCase):
    def test_consolidada_junta_a_demanda_e_as_respostas(self):
        sessao = Sessao("a demanda")
        sessao.registrar("pessoa", "a demanda")
        sessao.estado = EstadoDaSessao.PROBLEMATIZACAO
        sessao.registrar("sistema", "quem são os sujeitos?")
        sessao.registrar("pessoa", "jovens e adultos")

        self.assertEqual(sessao.consulta_consolidada(), "a demanda\njovens e adultos")

    def test_sem_problematizacao_a_consolidada_e_a_propria_demanda(self):
        sessao = Sessao("a demanda")
        sessao.registrar("pessoa", "a demanda")
        self.assertEqual(sessao.consulta_consolidada(), "a demanda")


if __name__ == "__main__":
    unittest.main()
