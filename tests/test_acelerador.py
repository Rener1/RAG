"""
Detecção do acelerador.

Decide qual build de `torch` instalar, e errar custa o download inteiro: o wheel
do acelerador errado instala sem reclamar e cai para CPU em silêncio. Como a
decisão acontece antes de qualquer instalação, ela precisa sair de arquivos do
kernel — o que a torna testável com um `/sys` de mentira.
"""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from apoio import *  # noqa: F401,F403  — põe src/ no sys.path

from rag.acelerador import arquiteturas_amd, detectar, nome_da_arquitetura  # noqa: E402


def falso_sys(*versoes: int) -> TemporaryDirectory:
    """Um `/sys/class/kfd/.../properties` de mentira, com as versões dadas."""
    pasta = TemporaryDirectory()
    for numero, versao in enumerate(versoes, start=1):
        no = Path(pasta.name) / str(numero)
        no.mkdir()
        (no / "properties").write_text(f"cpu_cores_count 0\ngfx_target_version {versao}\nsimd_count 128\n")
    return pasta


class TestNomeDaArquitetura(unittest.TestCase):
    def test_decodifica_o_formato_do_kernel(self):
        """maior*10000 + menor*100 + passo, com menor e passo em hexadecimal."""
        self.assertEqual(nome_da_arquitetura(120001), "gfx1201")  # RX 9070, RDNA4
        self.assertEqual(nome_da_arquitetura(100306), "gfx1036")  # iGPU Granite Ridge
        self.assertEqual(nome_da_arquitetura(110000), "gfx1100")  # RX 7900 XTX

    def test_passo_dez_vira_letra(self):
        """É o passo 10 escrito como 'a' que dá nome à família gfx90a."""
        self.assertEqual(nome_da_arquitetura(90010), "gfx90a")


class TestLeituraDoKernel(unittest.TestCase):
    def test_le_as_arquiteturas_presentes(self):
        with falso_sys(120001, 100306) as pasta:
            self.assertEqual(arquiteturas_amd(Path(pasta)), ["gfx1201", "gfx1036"])

    def test_no_de_cpu_reporta_zero_e_e_ignorado(self):
        with falso_sys(0, 120001) as pasta:
            self.assertEqual(arquiteturas_amd(Path(pasta)), ["gfx1201"])

    def test_a_mesma_gpu_em_dois_nos_conta_uma_vez(self):
        with falso_sys(120001, 120001) as pasta:
            self.assertEqual(arquiteturas_amd(Path(pasta)), ["gfx1201"])

    def test_maquina_sem_amd_devolve_vazio(self):
        self.assertEqual(arquiteturas_amd(Path("/nao/existe")), [])


class TestDeteccao(unittest.TestCase):
    def test_nvidia_tem_precedencia(self):
        with falso_sys(120001) as pasta:
            a = detectar(Path(pasta), tem_nvidia=True)
        self.assertEqual(a.tipo, "cuda")
        self.assertIn("cu", a.indice_torch)

    def test_amd_suportada_escolhe_a_rocm_minima(self):
        with falso_sys(120001) as pasta:
            a = detectar(Path(pasta), tem_nvidia=False)
        self.assertEqual(a.tipo, "rocm")
        self.assertTrue(a.indice_torch.endswith("rocm7.2"), a.indice_torch)

    def test_com_duas_gpus_manda_a_que_exige_mais(self):
        """O índice maior serve as duas; o menor deixaria a mais nova de fora."""
        with falso_sys(110000, 120001) as pasta:
            a = detectar(Path(pasta), tem_nvidia=False)
        self.assertTrue(a.indice_torch.endswith("rocm7.2"), a.indice_torch)

    def test_amd_desconhecida_cai_em_cpu_com_aviso(self):
        """Melhor perder velocidade do que baixar seis gigabytes que não funcionam."""
        with falso_sys(999999) as pasta:
            a = detectar(Path(pasta), tem_nvidia=False)
        self.assertEqual(a.tipo, "cpu")
        self.assertTrue(a.aviso)

    def test_sem_acelerador_nenhum(self):
        a = detectar(Path("/nao/existe"), tem_nvidia=False)
        self.assertEqual(a.tipo, "cpu")
        self.assertFalse(a.acelerado)
        self.assertFalse(a.aviso, "ausência de GPU não é anomalia, não deve avisar")

    def test_o_indice_e_sempre_uma_url_utilizavel(self):
        for nvidia in (True, False):
            a = detectar(Path("/nao/existe"), tem_nvidia=nvidia)
            self.assertTrue(a.indice_torch.startswith("https://"), a.indice_torch)


if __name__ == "__main__":
    unittest.main()
