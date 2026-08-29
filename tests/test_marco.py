"""
O marco pedagógico: leitura, validação e entrada no prompt.

O que estes testes protegem não é só o analisador. É a promessa de que o marco
pode ser editado por quem não programa: cada erro precisa dizer o que está
errado, em que arquivo, e o que fazer — senão "editável sem deploy" vira
"editável desde que um programador esteja por perto".
"""

import tempfile
import unittest
from pathlib import Path

from apoio import GeradorFalso, MarcoFalso  # noqa: F401  — também põe src/ no sys.path

from rag import marco as marco_pedagogico  # noqa: E402
from rag.erros import ErroMarcoInvalido  # noqa: E402
from rag.etapas.geracao import (  # noqa: E402
    montador_do_marco,
    montar_prompt_com_marco,
    validar_citacoes,
)
from rag.modelos import TrechoRecuperado  # noqa: E402
from rag.orquestrador import MotorRag  # noqa: E402
from rag.protocolos import MarcoPedagogico  # noqa: E402

PASTA_DE_MARCOS = Path(__file__).resolve().parents[1] / "marcos"

VALIDO = """---
nome: Marco de teste
versao: 2
autoria: quem escreveu
colecao_recomendada: acervo_x
---

Nota de quem escreve, antes da primeira seção — o sistema ignora.

## Papel
o papel

## Instruções
as instruções

## Formato de saída
o formato

## Triagem
como triar
"""


def trecho(numero: int) -> TrechoRecuperado:
    return TrechoRecuperado(
        texto=f"texto {numero}",
        titulo_pagina=f"Página {numero}",
        documento_origem=f"doc{numero}.txt",
        chunk_id=f"doc{numero}.txt::0",
        score=0.9,
    )


class TestAnalise(unittest.TestCase):
    def test_marco_valido_carrega_com_metadados_e_secoes(self):
        marco = marco_pedagogico.analisar(VALIDO, "teste")
        self.assertEqual(marco.nome, "Marco de teste")
        self.assertEqual(marco.versao, "2")
        self.assertEqual(marco.autoria, "quem escreveu")
        self.assertEqual(marco.metadados["colecao_recomendada"], "acervo_x")
        self.assertEqual(marco.secao("papel"), "o papel")
        self.assertEqual(marco.secao("Formato de saída"), "o formato")

    def test_nota_antes_da_primeira_secao_e_ignorada(self):
        marco = marco_pedagogico.analisar(VALIDO, "teste")
        self.assertNotIn("Nota de quem escreve", "".join(marco.secoes.values()))

    def test_titulo_com_acento_e_maiuscula_vira_a_mesma_secao(self):
        self.assertEqual(marco_pedagogico.normalizar_nome_de_secao("Formato de Saída"), "formato_de_saida")
        self.assertEqual(marco_pedagogico.normalizar_nome_de_secao("  instruções  "), "instrucoes")

    def test_secao_ausente_devolve_o_padrao(self):
        marco = marco_pedagogico.analisar(VALIDO, "teste")
        self.assertEqual(marco.secao("problematizacao", "nada"), "nada")

    def test_cumpre_o_protocolo(self):
        self.assertIsInstance(marco_pedagogico.analisar(VALIDO, "teste"), MarcoPedagogico)


class TestValidacao(unittest.TestCase):
    def test_sem_bloco_de_identificacao(self):
        with self.assertRaises(ErroMarcoInvalido) as capturado:
            marco_pedagogico.analisar("## Papel\ntexto\n", "teste")
        self.assertIn("---", capturado.exception.sugestao)

    def test_bloco_de_identificacao_aberto_e_nao_fechado(self):
        with self.assertRaises(ErroMarcoInvalido) as capturado:
            marco_pedagogico.analisar("---\nnome: x\n\n## Papel\ntexto\n", "teste")
        self.assertIn("fechado", str(capturado.exception))

    def test_campo_obrigatorio_faltando_e_nomeado(self):
        conteudo = VALIDO.replace("autoria: quem escreveu\n", "")
        with self.assertRaises(ErroMarcoInvalido) as capturado:
            marco_pedagogico.analisar(conteudo, "teste")
        self.assertIn("autoria", str(capturado.exception))

    def test_secao_obrigatoria_faltando_lista_as_encontradas(self):
        conteudo = VALIDO.replace("## Formato de saída\no formato\n", "")
        with self.assertRaises(ErroMarcoInvalido) as capturado:
            marco_pedagogico.analisar(conteudo, "teste", Path("teste.md"))
        self.assertIn("formato_de_saida", str(capturado.exception))
        self.assertIn("teste.md", str(capturado.exception))
        self.assertIn("papel", capturado.exception.sugestao)

    def test_secao_obrigatoria_vazia_e_erro(self):
        conteudo = VALIDO.replace("## Papel\no papel", "## Papel\n")
        with self.assertRaises(ErroMarcoInvalido) as capturado:
            marco_pedagogico.analisar(conteudo, "teste")
        self.assertIn("vazia", str(capturado.exception))


class TestDiretorio(unittest.TestCase):
    def test_identificador_inexistente_lista_os_disponiveis(self):
        with tempfile.TemporaryDirectory() as pasta:
            (Path(pasta) / "existente.md").write_text(VALIDO, encoding="utf-8")
            with self.assertRaises(ErroMarcoInvalido) as capturado:
                marco_pedagogico.carregar("inventado", Path(pasta))
            self.assertIn("existente", capturado.exception.sugestao)

    def test_leia_me_nao_conta_como_marco(self):
        with tempfile.TemporaryDirectory() as pasta:
            (Path(pasta) / "um.md").write_text(VALIDO, encoding="utf-8")
            (Path(pasta) / "LEIA-ME.md").write_text("# instruções\n", encoding="utf-8")
            self.assertEqual(marco_pedagogico.listar(Path(pasta)), ["um"])


class TestMarcosDoRepositorio(unittest.TestCase):
    """Impede que um `.md` quebrado seja commitado sem ninguém perceber."""

    def test_todos_os_marcos_versionados_carregam(self):
        identificadores = marco_pedagogico.listar(PASTA_DE_MARCOS)
        self.assertIn("generico", identificadores)
        self.assertIn("freiriano", identificadores)
        for identificador in identificadores:
            with self.subTest(marco=identificador):
                marco_pedagogico.carregar(identificador, PASTA_DE_MARCOS)

    def test_o_marco_padrao_traz_as_secoes_de_orquestracao(self):
        """Sem elas, mediação e sessão caem no comportamento genérico em silêncio."""
        marco = marco_pedagogico.carregar("generico", PASTA_DE_MARCOS)
        for secao in marco_pedagogico.SECOES_DE_ORQUESTRACAO:
            self.assertTrue(marco.secao(secao), f"'{secao}' vazia em generico.md")


class TestPromptComMarco(unittest.TestCase):
    def test_o_prompt_traz_as_secoes_a_pergunta_e_os_trechos(self):
        marco = MarcoFalso({"Papel": "o papel", "Recusas": "as recusas"})
        prompt = montar_prompt_com_marco(marco, "a pergunta", [trecho(1)])

        self.assertIn("PAPEL", prompt)
        self.assertIn("o papel", prompt)
        self.assertIn("as recusas", prompt)
        self.assertIn("a pergunta", prompt)
        self.assertIn("[Fonte 1: Página 1]", prompt)

    def test_secoes_de_orquestracao_ficam_fora_do_prompt_de_resposta(self):
        marco = marco_pedagogico.analisar(VALIDO, "teste")
        self.assertNotIn("como triar", montar_prompt_com_marco(marco, "p", [trecho(1)]))

    def test_secao_nova_do_comite_entra_sem_mexer_em_codigo(self):
        conteudo = VALIDO + "\n## Matriz de contradição\ncomo montar a matriz\n"
        marco = marco_pedagogico.analisar(conteudo, "teste")
        self.assertIn("como montar a matriz", montar_prompt_com_marco(marco, "p", [trecho(1)]))

    def test_o_montador_encaixa_no_motor_sem_alterar_o_orquestrador(self):
        gerador = GeradorFalso()
        marco = MarcoFalso({"Papel": "papel marcado"})
        motor = MotorRag(RecuperadorFixo([trecho(1)]), gerador, montador_do_marco(marco))

        motor.responder("uma pergunta")

        self.assertIn("papel marcado", gerador.ultimo_prompt)
        self.assertIn("uma pergunta", gerador.ultimo_prompt)


class TestValidacaoDeCitacoes(unittest.TestCase):
    def test_citacao_existente_passa(self):
        self.assertEqual(validar_citacoes("Como diz [Fonte 1: Página 1].", [trecho(1)]), [])

    def test_citacao_fora_da_faixa_e_apontada(self):
        self.assertEqual(validar_citacoes("Segundo [Fonte 9: Inventada].", [trecho(1)]), ["Fonte 9"])

    def test_fonte_zero_nao_passa(self):
        self.assertEqual(len(validar_citacoes("[Fonte 0]", [trecho(1)])), 1)

    def test_fontes_agrupadas_num_colchete_so_sao_todas_verificadas(self):
        """O modelo agrupa com frequência; a segunda fonte não pode escapar."""
        texto = "[Fonte 1: Válida, Fonte 2: Válida, Fonte 7: Inventada]"
        self.assertEqual(validar_citacoes(texto, [trecho(1), trecho(2)]), ["Fonte 7"])

    def test_texto_sem_citacao_nao_gera_alarme(self):
        self.assertEqual(validar_citacoes("resposta sem fonte nenhuma", [trecho(1)]), [])


class RecuperadorFixo:
    """Recuperador de uma linha só — o suficiente para fechar o ciclo aqui."""

    def __init__(self, trechos: list[TrechoRecuperado]) -> None:
        self._trechos = trechos

    def buscar(self, pergunta: str, k: int | None = None) -> list[TrechoRecuperado]:
        return self._trechos


if __name__ == "__main__":
    unittest.main()
