import unittest

from rag.config import ConfigNormalizacao
from rag.normalizacao_texto import blocos_do_texto, normalizar_blocos

# Dicionário de mentira: conhece estas e nenhuma outra.
CONHECIDAS = {
    "educação", "educa", "sócio", "político", "adulto", "adultos", "de", "a", "o", "para", "texto",
    "uma", "frase", "pois", "depois", "e", "outra", "parecer",
}  # fmt: skip


def dicionario(palavras):
    return {p for p in palavras if p.lower() not in CONHECIDAS}


def normalizar(texto, dicionario_=dicionario, **regras):
    return normalizar_blocos(blocos_do_texto(texto), ConfigNormalizacao(**regras), dicionario_)


class TestJuncaoDePalavras(unittest.TestCase):
    def test_hifen_marcado_junta_mesmo_sem_dicionario(self):
        resultado = normalizar("a educa¬\nção de adultos", dicionario_=None)
        self.assertEqual(resultado.texto, "a educação de adultos")
        self.assertEqual(resultado.contagens, {"hifen_marcado": 1})

    def test_hifen_marcado_de_enclise_fica_com_dicionario(self):
        resultado = normalizar("o texto tornando¬\nse outra", dicionario_=lambda p: {x for x in p if x == "tornandose"})
        self.assertEqual(resultado.texto, "o texto tornando-se outra")

    def test_sem_hifen_nao_junta_pedaco_curto(self):
        self.assertEqual(normalizar("uma frase de\no va").texto, "uma frase de o va")

    def test_hifen_comum_junta_quando_a_junta_existe(self):
        self.assertEqual(normalizar("a educa-\nção de adultos").texto, "a educação de adultos")

    def test_hifen_junta_mesmo_com_as_duas_metades_existindo(self):
        self.assertEqual(normalizar("o texto de\npois").texto, "o texto de pois")
        self.assertEqual(normalizar("o texto de-\npois").texto, "o texto depois")

    def test_palavra_composta_fica_com_hifen(self):
        resultado = normalizar("o sócio-\npolítico")
        self.assertEqual(resultado.texto, "o sócio-político")
        self.assertEqual(resultado.contagens, {"hifen_mantido": 1})

    def test_sem_dicionario_o_hifen_comum_fica(self):
        self.assertEqual(normalizar("a educa-\nção", dicionario_=None).texto, "a educa-ção")

    def test_sem_hifen_junta_so_com_o_dicionario(self):
        self.assertEqual(normalizar("para adul\nto e outra").texto, "para adulto e outra")
        self.assertEqual(normalizar("para adul\nto e outra", dicionario_=None).texto, "para adul to e outra")

    def test_duas_palavras_que_existem_nao_se_juntam(self):
        # `de` + `pois` = `depois` existe, mas as duas metades também
        self.assertEqual(normalizar("uma frase de\npois outra").texto, "uma frase de pois outra")

    def test_maiuscula_no_comeco_da_linha_nao_continua_palavra(self):
        self.assertEqual(normalizar("texto educa-\nÇão").texto, "texto educa- Ção")

    def test_regra_desligada_nao_junta(self):
        resultado = normalizar("para adul\nto", juntar_sem_hifen=False)
        self.assertEqual(resultado.texto, "para adul to")

    def test_hifen_marcado_no_fim_da_regiao_vira_hifen(self):
        self.assertEqual(normalizar("a educa¬\n\nção").texto, "a educa-\n\nção")

    def test_exemplos_para_a_auditoria(self):
        resultado = normalizar("a educa¬\nção")
        self.assertEqual(resultado.exemplos["hifen_marcado"], ["educa¬ / ção"])


class TestParagrafosEPontuacao(unittest.TestCase):
    def test_linhas_de_um_bloco_viram_um_paragrafo(self):
        self.assertEqual(normalizar("uma frase\nde texto\n\noutra").texto, "uma frase de texto\n\noutra")

    def test_juntar_linhas_desligado_mantem_as_quebras(self):
        self.assertEqual(normalizar("uma frase\nde texto", juntar_linhas=False).texto, "uma frase\nde texto")

    def test_espaco_depois_da_pontuacao_colada(self):
        resultado = normalizar("dos adultos.De parecer,a frase")
        self.assertEqual(resultado.texto, "dos adultos. De parecer, a frase")
        self.assertEqual(resultado.contagens["pontuacao"], 2)

    def test_poupa_numero_sigla_email_e_endereco(self):
        texto = "custa 3.5 nos U.S.A. ipf@paulofreire.org www.paulofreire.org paulofreire.org.br Ph.D. FPF.OPF"
        self.assertEqual(normalizar(texto).texto, texto)

    def test_espacos_repetidos(self):
        self.assertEqual(normalizar("uma   frase \t de").texto, "uma frase de")


if __name__ == "__main__":
    unittest.main()
