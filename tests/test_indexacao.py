"""
Testes da indexação — retomada, validação de dimensão e isolamento de falha.

Rodam com dublês: nenhum Qdrant nem Ollama precisa estar de pé.
"""

import json
import tempfile
import unittest
from pathlib import Path

from apoio import EmbutidorFalso, RepositorioFalso

from rag.config import ConfigEmbedding
from rag.erros import ErroPreRequisito
from rag.etapas import indexacao
from rag.modelos import Chunk


def escrever_chunks(pasta: str, quantidade: int) -> Path:
    arquivo = Path(pasta) / "chunks.jsonl"
    with arquivo.open("w", encoding="utf-8") as f:
        for i in range(quantidade):
            chunk = Chunk(f"doc.txt::{i}", f"texto {i}", "doc.txt", "Doc", i)
            f.write(json.dumps(chunk.como_dicionario(), ensure_ascii=False) + "\n")
    return arquivo


class TestLeitura(unittest.TestCase):
    def test_le_e_conta_sem_carregar_tudo(self):
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = escrever_chunks(pasta, 10)
            self.assertEqual(indexacao.contar_chunks(arquivo), 10)
            self.assertEqual(len(list(indexacao.ler_chunks(arquivo))), 10)

    def test_linha_corrompida_vira_erro_explicado(self):
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = Path(pasta) / "chunks.jsonl"
            arquivo.write_text('{"chunk_id": "a"}\n', encoding="utf-8")
            with self.assertRaises(ErroPreRequisito) as contexto:
                list(indexacao.ler_chunks(arquivo))
            self.assertIn("chunking", contexto.exception.sugestao)

    def test_agrupa_em_lotes_do_tamanho_pedido(self):
        chunks = (Chunk(f"d::{i}", "t", "d", "D", i) for i in range(10))
        lotes = list(indexacao.agrupar(chunks, 3))
        self.assertEqual([len(lote) for lote in lotes], [3, 3, 3, 1])


class TestIndexacao(unittest.TestCase):
    def setUp(self):
        self.config = ConfigEmbedding(tamanho_lote=4, lotes_paralelos=2, dimensao=4)
        self.embutidor = EmbutidorFalso(dimensao=4)
        self.repositorio = RepositorioFalso()

    def _executar(self, quantidade=10, **extras):
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = escrever_chunks(pasta, quantidade)
            return indexacao.executar(self.config, self.embutidor, self.repositorio, arquivo, **extras)

    def test_indexa_todos_os_chunks(self):
        resultado = self._executar(10)
        self.assertEqual(resultado.processados, 10)
        self.assertEqual(self.repositorio.contar_pontos(), 10)

    def test_retomada_pula_o_que_ja_esta_indexado(self):
        """A parte cara é o embedding: chunk já indexado não pode ser reprocessado."""
        self.repositorio.pontos["doc.txt::0"] = Chunk("doc.txt::0", "t", "doc.txt", "Doc", 0)
        self.repositorio.pontos["doc.txt::1"] = Chunk("doc.txt::1", "t", "doc.txt", "Doc", 1)

        resultado = self._executar(10, retomar=True)

        self.assertEqual(resultado.ignorados, 2)
        self.assertEqual(resultado.processados, 8)
        embutidos = [texto for chamada in self.embutidor.chamadas for texto in chamada]
        self.assertNotIn("texto 0", embutidos)

    def test_sem_retomada_reprocessa_tudo(self):
        self.repositorio.pontos["doc.txt::0"] = Chunk("doc.txt::0", "t", "doc.txt", "Doc", 0)
        resultado = self._executar(5, retomar=False)
        self.assertEqual(resultado.ignorados, 0)
        self.assertEqual(resultado.processados, 5)

    def test_recriar_limpa_a_colecao_antes(self):
        self.repositorio.pontos["antigo::0"] = Chunk("antigo::0", "t", "a", "A", 0)
        self._executar(3, recriar_colecao=True)
        self.assertTrue(self.repositorio.recriado)
        self.assertNotIn("antigo::0", self.repositorio.pontos)

    def test_lote_que_falha_nao_derruba_a_execucao(self):
        """Um lote quebrado é registrado e relatado; os outros seguem."""
        original = self.embutidor.embutir
        chamadas = {"n": 0}

        def embutir_com_falha(textos):
            chamadas["n"] += 1
            if chamadas["n"] == 1:
                raise RuntimeError("lote quebrado")
            return original(textos)

        self.embutidor.embutir = embutir_com_falha
        resultado = self._executar(12)

        self.assertTrue(resultado.houve_falha)
        self.assertGreater(resultado.processados, 0)
        self.assertLess(resultado.processados, 12)

    def test_arquivo_ausente_vira_erro_explicado(self):
        with self.assertRaises(ErroPreRequisito):
            indexacao.executar(self.config, self.embutidor, self.repositorio, Path("/tmp/nao-existe-nunca.jsonl"))


if __name__ == "__main__":
    unittest.main()
