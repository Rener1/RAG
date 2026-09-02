"""
Detecção do acelerador da máquina, para instalar só o que ela usa.

O `torch` tem builds distintos e **não intercambiáveis** por tipo de acelerador
— CPU, ROCm (AMD) e CUDA (NVIDIA) —, escolhidos pelo índice de instalação. Um
build de ~6 GB para AMD não roda em máquina NVIDIA, e o build de CPU roda em
qualquer lugar mas é lento. Fixar um deles no `Containerfile` tornaria a imagem
específica de uma máquina, que é o contrário do motivo de haver container.

Este módulo lê o que o kernel já expõe e diz qual índice aquela máquina precisa.
Não instala nada, não importa `torch` e não depende dele: roda antes de existir
qualquer instalação, que é justamente quando a resposta é necessária.

O modo de falha que ele existe para evitar é caro e silencioso: o wheel errado
**instala sem reclamar** e cai para CPU sem avisar. Paga-se o download e não se
ganha a velocidade.
"""

import shutil
from dataclasses import dataclass
from pathlib import Path

INDICE_CPU = "https://download.pytorch.org/whl/cpu"
INDICE_CUDA = "https://download.pytorch.org/whl/cu124"

# Menor ROCm que suporta cada arquitetura AMD, da matriz de compatibilidade da
# AMD. Placa fora desta tabela cai em CPU de propósito: melhor perder velocidade
# do que baixar seis gigabytes que não vão funcionar.
#
# Ao acrescentar uma placa, confira a matriz oficial — a lista envelhece a cada
# geração, e o preço de errar é o download inteiro.
ROCM_MINIMO = {
    "gfx1200": "7.2",  # RDNA4 — RX 9060
    "gfx1201": "7.2",  # RDNA4 — RX 9070 / 9070 XT
    "gfx1100": "6.2",  # RDNA3 — RX 7900 XTX
    "gfx1101": "6.2",
    "gfx1102": "6.2",
    "gfx1030": "6.2",  # RDNA2 — RX 6800/6900
    "gfx90a": "6.2",  # CDNA2 — MI210
    "gfx942": "6.2",  # CDNA3 — MI300
}

CAMINHO_NOS_AMD = Path("/sys/class/kfd/kfd/topology/nodes")


@dataclass(frozen=True, slots=True)
class Acelerador:
    """O que a máquina tem, e o que instalar por causa disso."""

    tipo: str  # "rocm" | "cuda" | "cpu"
    detalhe: str
    indice_torch: str
    aviso: str = ""

    @property
    def acelerado(self) -> bool:
        return self.tipo != "cpu"


def nome_da_arquitetura(versao: int) -> str:
    """`gfx_target_version` do kernel vira o nome usado pela AMD.

    O número é `maior * 10000 + menor * 100 + passo`, e **menor e passo são um
    dígito hexadecimal cada**: 120001 vira gfx1201, e 90010 vira gfx90a — é o
    passo 10 escrito como "a" que dá o nome àquela família.
    """
    maior, resto = divmod(versao, 10000)
    menor, passo = divmod(resto, 100)
    return f"gfx{maior}{menor:x}{passo:x}"


def arquiteturas_amd(raiz: Path = CAMINHO_NOS_AMD) -> list[str]:
    """Arquiteturas das GPUs AMD que o kernel expõe, sem repetir.

    Lê `/sys/class/kfd`, que existe quando o driver `amdgpu` está carregado —
    o mesmo caminho que o Ollama usa. Não precisa de ROCm instalado.
    """
    if not raiz.is_dir():
        return []

    encontradas: list[str] = []
    for propriedades in sorted(raiz.glob("*/properties")):
        try:
            texto = propriedades.read_text(encoding="utf-8")
        except OSError:
            continue

        for linha in texto.splitlines():
            if not linha.startswith("gfx_target_version"):
                continue
            versao = int(linha.split()[1])
            # O nó da CPU reporta zero; só GPU interessa aqui.
            if versao:
                nome = nome_da_arquitetura(versao)
                if nome not in encontradas:
                    encontradas.append(nome)

    return encontradas


def torch_enxerga_a_gpu() -> tuple[bool, str]:
    """O `torch` instalado de fato usa a GPU? Só responde em tempo de execução.

    A pergunta não pode ser respondida no build de um container: `podman build`
    não monta `/dev/kfd` nem `/dev/dri`, então a resposta lá é sempre "não",
    mesmo com o wheel correto. É aqui, com os dispositivos presentes, que ela
    tem sentido.

    Importa porque o modo de falha é silencioso: o wheel do acelerador errado
    instala sem reclamar e cai para CPU sem avisar. A diferença aparece só no
    cronômetro — segundos por consulta em vez de décimos.
    """
    try:
        import torch
    except ImportError:
        return False, "torch não instalado"

    versao = getattr(torch, "__version__", "?")
    try:
        if torch.cuda.is_available():
            return True, f"torch {versao} usando {torch.cuda.get_device_name(0)}"
    except (RuntimeError, AssertionError) as erro:
        return False, f"torch {versao} não conseguiu abrir a GPU: {erro}"
    return False, f"torch {versao} rodando em CPU"


def detectar(raiz_amd: Path = CAMINHO_NOS_AMD, tem_nvidia: bool | None = None) -> Acelerador:
    """O acelerador desta máquina e o índice de `torch` correspondente."""
    if tem_nvidia is None:
        tem_nvidia = shutil.which("nvidia-smi") is not None or Path("/dev/nvidia0").exists()

    if tem_nvidia:
        return Acelerador("cuda", "GPU NVIDIA", INDICE_CUDA)

    arquiteturas = arquiteturas_amd(raiz_amd)
    suportadas = [a for a in arquiteturas if a in ROCM_MINIMO]

    if suportadas:
        # Com mais de uma GPU, manda a que exige a ROCm mais nova: o índice
        # maior serve as duas, o menor deixaria a mais nova de fora.
        versao = max(ROCM_MINIMO[a] for a in suportadas)
        return Acelerador(
            "rocm",
            f"GPU AMD {', '.join(suportadas)}",
            f"https://download.pytorch.org/whl/rocm{versao}",
        )

    if arquiteturas:
        return Acelerador(
            "cpu",
            f"GPU AMD {', '.join(arquiteturas)}",
            INDICE_CPU,
            aviso=(
                "Arquitetura fora da tabela de suporte conhecida — usando CPU. "
                "Confira a matriz da AMD e acrescente em `ROCM_MINIMO` se ela já for suportada."
            ),
        )

    return Acelerador("cpu", "nenhum acelerador detectado", INDICE_CPU)
