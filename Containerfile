# Imagem de execução do pipeline RAG.
#
# Dois estágios de propósito. O `base` tem só as três dependências leves e serve
# a quem não usa reordenação; o `reordenacao` acrescenta o torch com ROCm e o
# cross-encoder, que juntos passam de 5 GB. Quem não precisa não baixa.
#
#   podman build -t rag:base --target execucao .
#   podman build -t rag:reordenacao --target reordenacao .
#
# O desenvolvimento continua no host: esta imagem é para executar e para
# reproduzir o ambiente noutra máquina.

FROM docker.io/library/python:3.14-slim AS base

# `PYTHONUNBUFFERED` mantém a barra de progresso e o texto gerado saindo
# conforme acontecem; sem isso o container parece travado nas etapas longas.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_ROOT_USER_ACTION=ignore

WORKDIR /app

# As três dependências leves ficam numa camada só, reaproveitada entre builds.
#
# O `gcc` entra e sai na mesma camada: `mwparserfromhell` compila um tokenizador
# em C, e a imagem `slim` não traz compilador. Instalar e purgar no mesmo `RUN`
# evita que ele fique nas camadas finais — e mantém a extensão em C, que a
# alternativa (`WITH_EXTENSION=0`) trocaria por uma implementação em Python puro,
# bem mais lenta na etapa de download.
COPY requirements-base.txt .
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libc6-dev \
    && pip install --no-cache-dir -r requirements-base.txt \
    && apt-get purge -y gcc libc6-dev \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# `data/`, `marcos/` e `avaliacao/` entram por montagem, não por cópia: são
# estado e conteúdo editável, e precisam sobreviver à troca de imagem.


# ── imagem leve, pronta para uso ─────────────────────────────────────────────
FROM base AS execucao

# **Tudo o que é leve e muda com frequência entra por último, e isso não é
# estética.** Cada camada invalida todas as seguintes, então `COPY src/`,
# `ENTRYPOINT` ou `CMD` no estágio `base` fariam uma edição de uma linha custar
# os ~6 GB do wheel do torch de novo, porque o estágio de reordenação deriva
# dele. Aconteceu duas vezes antes de eu entender.
COPY main.py .
COPY src/ src/

ENTRYPOINT ["python3", "main.py"]

# Sem argumento, o menu — igual ao host. O projeto tem ponto de entrada único, e
# um container que faz outra coisa quebra essa regra justamente para quem está
# conhecendo o sistema. Sem terminal o menu encerra limpo no EOF, então isso não
# atrapalha uso em script.
CMD []


# ── mesma coisa, com o cross-encoder de reordenação ──────────────────────────
FROM base AS reordenacao

# O `torch` tem builds distintos e **não intercambiáveis** por tipo de
# acelerador, escolhidos pelo índice de instalação. Uma imagem construída com o
# índice da AMD não roda em máquina NVIDIA, e vice-versa — fixar um deles aqui
# tornaria a imagem específica de uma máquina, que é o oposto do motivo de
# existir um container.
#
# O padrão é CPU porque roda em qualquer lugar. Aceleração é escolha de quem
# constrói:
#
#   AMD:    --build-arg TORCH_INDEX=https://download.pytorch.org/whl/rocm6.2
#   NVIDIA: --build-arg TORCH_INDEX=https://download.pytorch.org/whl/cu124
#
# Confira a matriz de suporte da sua placa antes: o wheel instala sem reclamar e
# cai para CPU em silêncio se a arquitetura não for suportada, que é o modo de
# falha mais caro — paga-se o download e não se ganha a velocidade.
ARG TORCH_INDEX=https://download.pytorch.org/whl/cpu

# A arquitetura da GPU desta máquina, para descartar os kernels das outras.
# `python3 main.py acelerador` imprime a sua; vazio mantém todos.
ARG GPU_ARCH=

# O wheel do ROCm embute kernels pré-compilados para **todas** as arquiteturas
# AMD suportadas — gfx90a, gfx942 (aceleradores de datacenter), gfx1030,
# gfx1100, gfx1201… Uma máquina usa uma. São vários gigabytes de `.co` que nunca
# serão carregados, e foi um deles (`..._gfx942.co`) que estourou o disco na
# primeira tentativa deste build.
#
# Apagar no mesmo `RUN` da instalação é o que faz a economia valer: em camadas
# separadas, o arquivo sai da imagem final mas continua pesando na camada de
# baixo.
#
# **Só entram na varredura arquivos que trazem `gfx` no nome.** Os que não
# trazem são índices compartilhados, e apagá-los rende
# "No library mapping found" do hipBLASLt a cada execução — um filtro por
# ausência de correspondência levaria o índice junto com os kernels alheios.
RUN pip install --no-cache-dir --index-url "${TORCH_INDEX}" torch \
    && pip install --no-cache-dir transformers \
    && if [ -n "${GPU_ARCH}" ]; then \
         find /usr/local/lib/python3.14/site-packages/torch/lib \
              \( -name '*gfx*.co' -o -name '*gfx*.dat' -o -name '*gfx*.hsaco' \) \
              ! -name "*${GPU_ARCH}*" -delete 2>/dev/null || true; \
       fi \
    && du -sh /usr/local/lib/python3.14/site-packages/torch

# Bibliotecas de sistema que o wheel do torch espera encontrar e que a imagem
# `slim` não traz — ela remove tudo que não é estritamente necessário ao Python.
# `libatomic1` é obrigatória para qualquer variante; as demais são do runtime
# ROCm. Instaladas **depois** do pip para que mexer aqui não invalide a camada
# do torch, que leva vários gigabytes para refazer.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libatomic1 libnuma1 libelf1 libdrm2 \
    && rm -rf /var/lib/apt/lists/*

# Registra qual build entrou, para a imagem saber o que ela é. **A verificação
# de que a GPU aparece não pode acontecer aqui**: `podman build` não passa
# dispositivos ao container de build, então `/dev/kfd` e `/dev/dri` não existem
# e `torch.cuda.is_available()` é falso por construção, mesmo com o wheel certo.
# Quem verifica é `main.py ambiente`, em tempo de execução, onde os dispositivos
# estão montados.
ARG TORCH_INDEX
ENV RAG_TORCH_INDEX=${TORCH_INDEX}
RUN python3 -c "import torch; print(f'torch {torch.__version__} instalado de ${TORCH_INDEX}')"

# Baixa o cross-encoder no build, e não no primeiro uso: assim o container roda
# offline e ninguém espera 2 GB na primeira pergunta.
ENV HF_HOME=/opt/modelos

RUN python3 -c "\
from transformers import AutoModelForSequenceClassification, AutoTokenizer; \
m='BAAI/bge-reranker-v2-m3'; \
AutoTokenizer.from_pretrained(m); \
AutoModelForSequenceClassification.from_pretrained(m)"

# O modelo é baixado no build e vive na imagem, então em execução não há nada a
# buscar no Hub. Sem `HF_HUB_OFFLINE` o `transformers` consulta a rede a cada
# execução e imprime um aviso sobre requisições não autenticadas — ruído numa
# operação que sequer deveria acontecer. Isto também faz o container funcionar
# sem rede, que é requisito de um sistema pensado para rodar localmente.
ENV HF_HUB_OFFLINE=1 \
    HF_HUB_DISABLE_PROGRESS_BARS=1 \
    TRANSFORMERS_VERBOSITY=error \
    TOKENIZERS_PARALLELISM=false

# O código e a configuração de entrada por último aqui também, pelo mesmo motivo.
COPY main.py .
COPY src/ src/

ENTRYPOINT ["python3", "main.py"]
CMD []
