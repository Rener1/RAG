"""
A camada de mediação entre a pergunta e o embedding.

Dois pontos concentram o risco. O primeiro é o fallback: a mediação usa o modelo
de geração, e a recuperação precisa continuar avaliável sozinha mesmo com esse
modelo fora do ar — por isso nenhum tropeço aqui pode virar exceção. O segundo é
a fusão: RRF é curto o bastante para parecer óbvio e errado o bastante para
passar despercebido, então há um caso com a conta feita à mão.
"""

import unittest

from apoio import EmbutidorPorTexto, GeradorFalso, GeradorRoteirizado, RecuperadorFalso  # noqa: F401

from rag.config import ConfigBusca, ConfigIntermediacao  # noqa: E402
from rag.erros import ErroConexao  # noqa: E402
from rag.mediacao import (  # noqa: E402
    ConsultaDecomposta,
    IntermediadorDeConsulta,
    descartar_redundantes,
    extrair_subconsultas,
    fundir_por_rrf,
    limitar_por_documento,
    similaridade,
)
from rag.modelos import TrechoRecuperado  # noqa: E402
from rag.orquestrador import MotorRag  # noqa: E402
from rag.protocolos import RecuperadorDeTrechos  # noqa: E402

PERGUNTA = "quem são os argonianos e qual a relação deles com os hist?"


def trecho(identificador: str, score: float = 0.9, documento: str = "") -> TrechoRecuperado:
    return TrechoRecuperado(
        texto=f"texto {identificador}",
        titulo_pagina=identificador,
        documento_origem=documento or f"{identificador}.txt",
        chunk_id=identificador,
        score=score,
    )


def montar(gerador, recuperador, embutidor=None, busca=None, **ajustes) -> IntermediadorDeConsulta:
    """Intermediador com dublês.

    `limiar_relativo=0` é explícito porque o padrão do projeto liga a quantidade
    dinâmica, e a maioria destes testes verifica o `k` fixo.
    """
    config = ConfigIntermediacao(**ajustes)
    busca = busca or ConfigBusca(k=3, limiar_relativo=0.0)
    return IntermediadorDeConsulta(recuperador, gerador, embutidor or EmbutidorPorTexto(), config, busca)


class TestExtracao(unittest.TestCase):
    def test_lista_numerada(self):
        saida = "1. quem são os argonianos\n2. o que são os hist\n3. relação entre eles"
        self.assertEqual(len(extrair_subconsultas(saida, 3, PERGUNTA)), 3)

    def test_lista_com_traco_e_com_ponto(self):
        saida = "- quem são os argonianos\n• o que são os hist"
        self.assertEqual(extrair_subconsultas(saida, 3, PERGUNTA), ["quem são os argonianos", "o que são os hist"])

    def test_linha_que_repete_a_pergunta_e_descartada(self):
        saida = f"{PERGUNTA}\no que são os hist"
        self.assertEqual(extrair_subconsultas(saida, 3, PERGUNTA), ["o que são os hist"])

    def test_eco_do_prompt_e_descartado(self):
        saida = "Claro, aqui estão as sub-consultas:\nquem são os argonianos"
        self.assertEqual(extrair_subconsultas(saida, 3, PERGUNTA), ["quem são os argonianos"])

    def test_linha_curta_ou_longa_demais_e_descartada(self):
        saida = "ok\n" + ("x" * 300) + "\numa consulta de tamanho razoável"
        self.assertEqual(extrair_subconsultas(saida, 3, PERGUNTA), ["uma consulta de tamanho razoável"])

    def test_repetidas_ignorando_caixa_contam_uma_vez(self):
        saida = "Quem São Os Argonianos\nquem são os argonianos"
        self.assertEqual(len(extrair_subconsultas(saida, 3, PERGUNTA)), 1)

    def test_respeita_o_maximo_mesmo_com_o_modelo_falante(self):
        saida = "\n".join(f"consulta número {n} sobre o assunto" for n in range(10))
        self.assertEqual(len(extrair_subconsultas(saida, 3, PERGUNTA)), 3)

    def test_lixo_devolve_vazio(self):
        self.assertEqual(extrair_subconsultas("...\n\n?\n", 3, PERGUNTA), [])


class TestFusao(unittest.TestCase):
    def test_presente_em_mais_rankings_sobe(self):
        """b é 2º em ambos; a é 1º num só. 2/62 > 1/61, então b vem na frente."""
        rankings = [
            [trecho("a", 0.99), trecho("b", 0.50)],
            [trecho("c", 0.98), trecho("b", 0.50)],
        ]
        self.assertEqual([t.chunk_id for t in fundir_por_rrf(rankings)], ["b", "a", "c"])

    def test_deduplica_por_chunk_id(self):
        rankings = [[trecho("a")], [trecho("a")], [trecho("a")]]
        self.assertEqual(len(fundir_por_rrf(rankings)), 1)

    def test_preserva_a_melhor_similaridade_original(self):
        fundidos = fundir_por_rrf([[trecho("a", 0.40)], [trecho("a", 0.80)]])
        self.assertAlmostEqual(fundidos[0].score, 0.80)

    def test_ranking_unico_preserva_a_ordem(self):
        rankings = [[trecho("a", 0.9), trecho("b", 0.8), trecho("c", 0.7)]]
        self.assertEqual([t.chunk_id for t in fundir_por_rrf(rankings)], ["a", "b", "c"])

    def test_sem_rankings_devolve_vazio(self):
        self.assertEqual(fundir_por_rrf([]), [])
        self.assertEqual(fundir_por_rrf([[], []]), [])

    def test_empate_e_desfeito_de_forma_estavel(self):
        rankings = [[trecho("a", 0.5)], [trecho("b", 0.9)]]
        primeira = [t.chunk_id for t in fundir_por_rrf(rankings)]
        self.assertEqual(primeira, [t.chunk_id for t in fundir_por_rrf(rankings)])
        self.assertEqual(primeira[0], "b", "empate deveria ir para a maior similaridade")


class TestDiversidade(unittest.TestCase):
    def test_teto_por_documento(self):
        trechos = [trecho(f"t{n}", documento="mesmo.txt") for n in range(4)] + [trecho("outro", documento="outro.txt")]
        limitados = limitar_por_documento(trechos, 2)
        self.assertEqual([t.chunk_id for t in limitados], ["t0", "t1", "outro"])

    def test_teto_zero_nao_limita(self):
        trechos = [trecho(f"t{n}", documento="mesmo.txt") for n in range(4)]
        self.assertEqual(len(limitar_por_documento(trechos, 0)), 4)


class TestIntermediador(unittest.TestCase):
    def test_cumpre_o_protocolo_de_recuperacao(self):
        intermediador = montar(GeradorRoteirizado(), RecuperadorFalso())
        self.assertIsInstance(intermediador, RecuperadorDeTrechos)

    def test_decompoe_e_busca_cada_subconsulta(self):
        gerador = GeradorRoteirizado(["quem são os argonianos\no que são os hist"])
        recuperador = RecuperadorFalso(padrao=[trecho("a")])
        intermediador = montar(gerador, recuperador, decompor=True, incluir_pergunta_original=True)

        intermediador.buscar(PERGUNTA)

        consultadas = [consulta for consulta, _ in recuperador.consultas]
        self.assertEqual(consultadas, [PERGUNTA, "quem são os argonianos", "o que são os hist"])

    def test_desligada_repassa_direto_sem_chamar_o_modelo(self):
        gerador = GeradorRoteirizado(["não deveria ser chamado"])
        recuperador = RecuperadorFalso(padrao=[trecho("a")])
        intermediador = montar(gerador, recuperador, ligada=False)

        intermediador.buscar(PERGUNTA, k=7)

        self.assertEqual(gerador.prompts, [])
        self.assertEqual(recuperador.consultas, [(PERGUNTA, 7)])

    def test_pergunta_curta_nao_paga_uma_chamada_ao_modelo(self):
        gerador = GeradorRoteirizado(["não deveria ser chamado"])
        recuperador = RecuperadorFalso(padrao=[trecho("a")])
        intermediador = montar(gerador, recuperador, decompor=True, minimo_de_caracteres=25)

        consulta = intermediador.decompor("quem é Ysgramor?")

        self.assertEqual(gerador.prompts, [])
        self.assertFalse(consulta.veio_do_modelo)
        self.assertIn("curta", consulta.motivo_do_fallback)

    def test_gerador_fora_do_ar_nao_derruba_a_busca(self):
        """A recuperação precisa continuar avaliável sem o modelo de geração."""
        gerador = GeradorRoteirizado(erro=ErroConexao("Ollama fora do ar"))
        recuperador = RecuperadorFalso(padrao=[trecho("a")])
        intermediador = montar(gerador, recuperador, decompor=True)

        resultado = intermediador.buscar(PERGUNTA, k=2)

        self.assertEqual(recuperador.consultas, [(PERGUNTA, 2)])
        self.assertEqual([t.chunk_id for t in resultado], ["a"])

    def test_saida_ilegivel_do_modelo_vira_busca_direta(self):
        gerador = GeradorRoteirizado(["...\n?\n"])
        recuperador = RecuperadorFalso(padrao=[trecho("a")])
        intermediador = montar(gerador, recuperador, decompor=True)

        intermediador.buscar(PERGUNTA, k=4)

        self.assertEqual(recuperador.consultas, [(PERGUNTA, 4)], "fallback deve ser uma busca só, igual à direta")

    def test_avisa_a_interface_antes_de_buscar(self):
        vistas: list[ConsultaDecomposta] = []
        gerador = GeradorRoteirizado(["uma consulta razoável\noutra consulta razoável"])
        intermediador = IntermediadorDeConsulta(
            RecuperadorFalso(padrao=[trecho("a")]),
            gerador,
            EmbutidorPorTexto(),
            ConfigIntermediacao(decompor=True),
            ConfigBusca(),
            ao_decompor=vistas.append,
        )

        intermediador.buscar(PERGUNTA)

        self.assertEqual(len(vistas), 1)
        self.assertTrue(vistas[0].houve_decomposicao)
        self.assertEqual(vistas[0].original, PERGUNTA)

    def test_orientacao_do_marco_chega_ao_prompt(self):
        gerador = GeradorRoteirizado(["uma consulta razoável"])
        intermediador = IntermediadorDeConsulta(
            RecuperadorFalso(),
            gerador,
            EmbutidorPorTexto(),
            ConfigIntermediacao(decompor=True),
            ConfigBusca(),
            orientacao_do_marco="procure sempre a posição contrária",
        )

        intermediador.decompor(PERGUNTA)

        self.assertIn("procure sempre a posição contrária", gerador.prompts[0])

    def test_corta_no_k_pedido(self):
        gerador = GeradorRoteirizado(["primeira consulta razoável\nsegunda consulta razoável"])
        recuperador = RecuperadorFalso(padrao=[trecho(f"t{n}") for n in range(10)])
        intermediador = montar(gerador, recuperador, decompor=True)

        self.assertEqual(len(intermediador.buscar(PERGUNTA, k=2)), 2)

    def test_sem_k_usa_o_da_configuracao_de_busca(self):
        gerador = GeradorRoteirizado(["primeira consulta razoável\nsegunda consulta razoável"])
        recuperador = RecuperadorFalso(padrao=[trecho(f"t{n}") for n in range(10)])
        intermediador = montar(gerador, recuperador, decompor=True)  # ConfigBusca(k=3)

        self.assertEqual(len(intermediador.buscar(PERGUNTA)), 3)

    def test_fecha_o_ciclo_rag_sem_o_motor_saber_da_camada(self):
        gerador_da_resposta = GeradorFalso()
        intermediador = montar(
            GeradorRoteirizado(["primeira consulta razoável\nsegunda consulta razoável"]),
            RecuperadorFalso(padrao=[trecho("a")]),
            decompor=True,
        )

        resposta = MotorRag(intermediador, gerador_da_resposta).responder(PERGUNTA)

        self.assertEqual(resposta.texto, "resposta gerada")
        self.assertEqual([t.chunk_id for t in resposta.trechos], ["a"])


class TestRedundancia(unittest.TestCase):
    """O número de sub-consultas é dinâmico porque as redundantes caem fora.

    É o caso que motivou a mudança: "O que diz a lenda do dragonborn?" produzia
    'lenda dragonborn', 'conteúdo da lenda dragonborn' e 'significado da lenda
    dragonborn' — três vetores quase iguais e duas buscas jogadas fora.
    """

    def test_similaridade_de_vetores_iguais_e_um(self):
        self.assertAlmostEqual(similaridade([1.0, 0.0], [1.0, 0.0]), 1.0)

    def test_similaridade_de_ortogonais_e_zero(self):
        self.assertAlmostEqual(similaridade([1.0, 0.0], [0.0, 1.0]), 0.0)

    def test_vetor_nulo_nao_estoura(self):
        self.assertEqual(similaridade([0.0, 0.0], [1.0, 0.0]), 0.0)

    def test_parafrases_colapsam_numa_consulta_so(self):
        parecido = [1.0, 0.05, 0.0]
        embutidor = EmbutidorPorTexto(
            {
                "lenda dragonborn": [1.0, 0.0, 0.0],
                "conteúdo da lenda dragonborn": parecido,
                "significado da lenda dragonborn": parecido,
            }
        )
        aceitas, descartadas = descartar_redundantes(
            ["lenda dragonborn", "conteúdo da lenda dragonborn", "significado da lenda dragonborn"],
            embutidor,
            0.90,
        )
        self.assertEqual(aceitas, ["lenda dragonborn"])
        self.assertEqual(descartadas, 2)

    def test_facetas_distintas_sobrevivem(self):
        aceitas, descartadas = descartar_redundantes(
            ["quem são os argonianos", "o que são os hist"], EmbutidorPorTexto(), 0.90
        )
        self.assertEqual(len(aceitas), 2)
        self.assertEqual(descartadas, 0)

    def test_a_primeira_do_par_e_a_que_fica(self):
        """A pergunta original vem primeira, então nunca é a descartada."""
        igual = [1.0, 0.0]
        embutidor = EmbutidorPorTexto({"original": igual, "cópia": igual})
        aceitas, _ = descartar_redundantes(["original", "cópia"], embutidor, 0.90)
        self.assertEqual(aceitas, ["original"])

    def test_limiar_em_um_nao_descarta_nada(self):
        igual = [1.0, 0.0]
        embutidor = EmbutidorPorTexto({"a": igual, "b": igual})
        aceitas, descartadas = descartar_redundantes(["a", "b"], embutidor, 1.0)
        self.assertEqual(len(aceitas), 2)
        self.assertEqual(descartadas, 0)

    def test_uma_consulta_so_nem_chama_o_embutidor(self):
        embutidor = EmbutidorPorTexto()
        descartar_redundantes(["única"], embutidor, 0.90)
        self.assertEqual(embutidor.chamadas, [])

    def test_embutidor_fora_do_ar_devolve_a_lista_intacta(self):
        """A recuperação não pode parar por causa de uma otimização."""
        embutidor = EmbutidorPorTexto()
        embutidor.erro = ErroConexao("Ollama fora do ar")
        aceitas, descartadas = descartar_redundantes(["a", "b", "c"], embutidor, 0.90)
        self.assertEqual(aceitas, ["a", "b", "c"])
        self.assertEqual(descartadas, 0)

    def test_um_embutir_so_para_todas_as_consultas(self):
        embutidor = EmbutidorPorTexto()
        descartar_redundantes(["a", "b", "c"], embutidor, 0.90)
        self.assertEqual(len(embutidor.chamadas), 1, "deveria ser um lote só")


class TestNumeroDinamicoDeConsultas(unittest.TestCase):
    def test_parafrases_viram_uma_busca_so(self):
        """O desfecho que importa: o mesmo custo de busca da consulta direta."""
        parecido = [1.0, 0.02, 0.0]
        embutidor = EmbutidorPorTexto(
            {PERGUNTA: [1.0, 0.0, 0.0], "lenda dragonborn": parecido, "conteúdo da lenda": parecido}
        )
        recuperador = RecuperadorFalso(padrao=[trecho("a")])
        intermediador = montar(
            GeradorRoteirizado(["lenda dragonborn\nconteúdo da lenda"]), recuperador, embutidor, decompor=True
        )

        intermediador.buscar(PERGUNTA, k=3)

        self.assertEqual(recuperador.consultas, [(PERGUNTA, 3)], "deveria ter feito uma busca só")

    def test_pergunta_composta_mantem_as_facetas(self):
        recuperador = RecuperadorFalso(padrao=[trecho("a")])
        intermediador = montar(
            GeradorRoteirizado(["quem são os argonianos\no que são os hist"]), recuperador, decompor=True
        )

        intermediador.buscar(PERGUNTA)

        self.assertEqual(len(recuperador.consultas), 3, "original + duas facetas distintas")

    def test_a_contagem_de_descartadas_chega_a_interface(self):
        parecido = [1.0, 0.02, 0.0]
        embutidor = EmbutidorPorTexto({PERGUNTA: [1.0, 0.0, 0.0], "uma variação qualquer": parecido})
        intermediador = montar(
            GeradorRoteirizado(["uma variação qualquer"]),
            RecuperadorFalso(padrao=[trecho("a")]),
            embutidor,
            decompor=True,
        )

        consulta = intermediador.decompor(PERGUNTA)

        self.assertEqual(consulta.descartadas_por_redundancia, 1)
        self.assertFalse(consulta.houve_decomposicao)


class TestCorteFinal(unittest.TestCase):
    """A mediação corta pela mesma política da busca direta.

    Regressão de um bug real: o corte era fixo em `config_busca.k`, então com a
    quantidade dinâmica ligada a busca direta devolvia 11 trechos e a mediada 8.
    Além de incoerente, tornava `avaliar --comparar` uma comparação entre
    quantidades diferentes — que não diz nada sobre a mediação.
    """

    def _intermediador(self, busca, quantos=20):
        trechos = [
            TrechoRecuperado(
                texto=f"t{n}", titulo_pagina=f"P{n}", documento_origem=f"{n}.txt", chunk_id=str(n), score=0.9
            )
            for n in range(quantos)
        ]
        return montar(
            GeradorRoteirizado(["primeira consulta razoável\nsegunda consulta razoável"]),
            RecuperadorFalso(padrao=trechos),
            busca=busca,
            decompor=True,
        )

    def test_aplica_a_politica_dinamica_como_a_busca_direta(self):
        busca = ConfigBusca(k=3, limiar_relativo=0.9, k_maximo=20, k_minimo=5)
        # Scores todos iguais: o limiar relativo mantém tudo até o teto.
        self.assertEqual(len(self._intermediador(busca).buscar(PERGUNTA)), 20)

    def test_respeita_o_piso_da_politica(self):
        busca = ConfigBusca(k=3, limiar_relativo=0.9, k_maximo=20, k_minimo=5)
        self.assertEqual(len(self._intermediador(busca, quantos=3).buscar(PERGUNTA)), 3)

    def test_sem_politica_dinamica_corta_no_k_configurado(self):
        busca = ConfigBusca(k=4, limiar_relativo=0.0)
        self.assertEqual(len(self._intermediador(busca).buscar(PERGUNTA)), 4)

    def test_k_explicito_manda_mesmo_com_politica_ligada(self):
        busca = ConfigBusca(k=3, limiar_relativo=0.9, k_maximo=20, k_minimo=5)
        self.assertEqual(len(self._intermediador(busca).buscar(PERGUNTA, k=6)), 6)


class TestTraducaoDaConsulta(unittest.TestCase):
    """Traduzir para o idioma do acervo — capacidade, não padrão.

    Nenhum marco do repositório declara `idioma_do_acervo` hoje: o papel da
    mediação é decompor pergunta composta. A capacidade fica porque o acervo do
    IPF pode vir com material em outro idioma, e porque medi que ela rende
    (+3 de recall, +5 de cobertura) quando o descasamento existe.

    Estes testes desligam a decomposição de propósito, para exercitar a tradução
    isolada.
    """

    def _intermediador(self, resposta, idioma="en", **ajustes):
        ajustes.setdefault("decompor", False)
        gerador = GeradorRoteirizado([resposta])
        intermediador = IntermediadorDeConsulta(
            RecuperadorFalso(padrao=[trecho("a")]),
            gerador,
            EmbutidorPorTexto(),
            ConfigIntermediacao(**ajustes),
            ConfigBusca(k=3, limiar_relativo=0.0),
            idioma_do_acervo=idioma,
        )
        return intermediador, gerador

    def test_o_prompt_pede_o_idioma_do_acervo(self):
        intermediador, gerador = self._intermediador("what are the Hist?")
        intermediador.decompor("o que são os Hist?")
        self.assertIn("inglês", gerador.prompts[0])

    def test_sem_idioma_declarado_nao_pede_traducao(self):
        intermediador, gerador = self._intermediador("consulta qualquer", idioma="", decompor=True)
        intermediador.decompor("uma pergunta suficientemente longa para passar da guarda")
        self.assertNotIn("Traduza", gerador.prompts[0])

    def test_sem_idioma_e_sem_decompor_nao_chama_o_modelo(self):
        """Não há o que preparar: seria uma chamada ao modelo por nada."""
        intermediador, gerador = self._intermediador("não deveria ser chamado", idioma="")
        consulta = intermediador.decompor("o que são os Hist?")
        self.assertEqual(gerador.prompts, [])
        self.assertEqual(consulta.subconsultas, ["o que são os Hist?"])

    def test_idioma_desconhecido_vai_como_veio(self):
        intermediador, gerador = self._intermediador("consulta", idioma="de")
        intermediador.decompor("o que são os Hist?")
        self.assertIn("para de", gerador.prompts[0])

    def test_sem_decompor_o_prompt_pede_uma_linha_so(self):
        intermediador, gerador = self._intermediador("what are the Hist?")
        intermediador.decompor("o que são os Hist?")
        self.assertIn("uma linha só", gerador.prompts[0])
        self.assertNotIn("uma linha por assunto", gerador.prompts[0])

    def test_o_prompt_traz_exemplos_de_nome_proprio_preservado(self):
        """Sem exemplo o modelo traduziu "Hist" por "histories" e destruiu a busca."""
        intermediador, gerador = self._intermediador("what are the Hist?", decompor=True)
        intermediador.decompor("o que são os Hist?")
        self.assertIn("-> what are the Hist?", gerador.prompts[0])

    def test_o_prompt_proibe_palavras_soltas(self):
        """Sopa de palavras-chave embute pior que a frase inteira."""
        intermediador, gerador = self._intermediador("what are the Hist?", decompor=True)
        intermediador.decompor("o que são os Hist?")
        self.assertIn("perguntas completas", gerador.prompts[0])

    def test_a_original_entra_junto_da_consulta_preparada(self):
        """Proteção medida contra tradução ruim.

        O modelo erra nome próprio com frequência — chegou a traduzir "Hist"
        (as árvores sencientes) por "Histories". Buscar só a tradução derrubou o
        recall de 88% para 85%; fundir as duas por RRF devolve os 88% e sobe a
        cobertura de 74% para 78%, porque a tradução ruim é diluída pelo voto da
        original e a boa acrescenta.
        """
        recuperador = RecuperadorFalso(padrao=[trecho("a")])
        intermediador = IntermediadorDeConsulta(
            recuperador,
            GeradorRoteirizado(["what are the Hist?"]),
            EmbutidorPorTexto(),
            ConfigIntermediacao(decompor=False, incluir_pergunta_original=True),
            ConfigBusca(k=3, limiar_relativo=0.0),
            idioma_do_acervo="en",
        )

        intermediador.buscar("o que são os Hist?")

        self.assertEqual([c for c, _ in recuperador.consultas], ["o que são os Hist?", "what are the Hist?"])

    def test_sem_a_original_busca_so_a_traducao(self):
        recuperador = RecuperadorFalso(padrao=[trecho("a")])
        IntermediadorDeConsulta(
            recuperador,
            GeradorRoteirizado(["what are the Hist?"]),
            EmbutidorPorTexto(),
            ConfigIntermediacao(decompor=False, incluir_pergunta_original=False),
            ConfigBusca(k=3, limiar_relativo=0.0),
            idioma_do_acervo="en",
        ).buscar("o que são os Hist?")

        self.assertEqual([c for c, _ in recuperador.consultas], ["what are the Hist?"])

    def test_a_orientacao_do_marco_chega_mesmo_sem_decompor(self):
        """É onde o comitê escreve o que a busca deve procurar."""
        gerador = GeradorRoteirizado(["what are the Hist?"])
        IntermediadorDeConsulta(
            RecuperadorFalso(),
            gerador,
            EmbutidorPorTexto(),
            ConfigIntermediacao(decompor=False),
            ConfigBusca(),
            orientacao_do_marco="procure sempre a posição contrária",
            idioma_do_acervo="en",
        ).decompor("o que são os Hist?")

        self.assertIn("procure sempre a posição contrária", gerador.prompts[0])

    def test_modelo_fora_do_ar_cai_na_pergunta_original(self):
        intermediador = IntermediadorDeConsulta(
            RecuperadorFalso(padrao=[trecho("a")]),
            GeradorRoteirizado(erro=ErroConexao("Ollama fora do ar")),
            EmbutidorPorTexto(),
            ConfigIntermediacao(decompor=False),
            ConfigBusca(k=3, limiar_relativo=0.0),
            idioma_do_acervo="en",
        )
        consulta = intermediador.decompor("o que são os Hist?")
        self.assertEqual(consulta.subconsultas, ["o que são os Hist?"])


if __name__ == "__main__":
    unittest.main()
