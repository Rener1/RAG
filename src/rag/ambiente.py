"""
Diagnóstico do ambiente.

Roda antes das etapas caras para transformar "falhou no meio depois de vinte
minutos" em "faltou baixar o modelo, o comando é este". Cada verificação
devolve um estado e uma sugestão de conserto; nada é corrigido automaticamente.
"""

from dataclasses import dataclass
from enum import StrEnum

from .config import Config
from .servico import Servico


class Estado(StrEnum):
    OK = "ok"
    AVISO = "aviso"
    FALHA = "falha"


@dataclass
class Verificacao:
    """Resultado de um item do diagnóstico."""

    nome: str
    estado: Estado
    detalhe: str
    sugestao: str = ""


def verificar(config: Config) -> list[Verificacao]:
    """Diagnóstico completo, na ordem em que o pipeline precisa das coisas."""
    servico = Servico(config)
    itens: list[Verificacao] = []

    # ── dependências Python ───────────────────────────────────────────────
    try:
        import mwparserfromhell  # noqa: F401
        import qdrant_client  # noqa: F401
        import requests  # noqa: F401

        itens.append(Verificacao("Dependências Python", Estado.OK, "requests, qdrant-client, mwparserfromhell"))
    except ImportError as erro:
        itens.append(Verificacao("Dependências Python", Estado.FALHA, str(erro), "pip3 install -r requirements.txt"))

    # ── Ollama e modelos ──────────────────────────────────────────────────
    disponivel, detalhe = servico.embutidor.esta_disponivel()
    if disponivel:
        itens.append(Verificacao("Ollama", Estado.OK, f"em {config.embedding.ollama_url}"))
        baixados = detalhe.split(", ")
        for papel, modelo in (("embedding", config.embedding.modelo), ("geração", config.geracao.modelo)):
            # O Ollama lista "bge-m3:latest" para quem pediu "bge-m3"; comparar
            # pelo prefixo evita falso negativo por causa da etiqueta.
            presente = any(m == modelo or m.startswith(f"{modelo}:") for m in baixados)
            itens.append(
                Verificacao(
                    f"Modelo de {papel} ({modelo})",
                    Estado.OK if presente else Estado.FALHA,
                    "baixado" if presente else "não encontrado",
                    "" if presente else f"ollama pull {modelo}",
                )
            )
    else:
        itens.append(Verificacao("Ollama", Estado.FALHA, detalhe, "Suba o Ollama — os modelos rodam através dele."))

    # ── banco vetorial ────────────────────────────────────────────────────
    disponivel, detalhe = servico.repositorio.esta_disponivel()
    if not disponivel:
        itens.append(Verificacao("Qdrant", Estado.FALHA, detalhe, "podman compose up -d   (podman, não docker)"))
    else:
        itens.append(Verificacao("Qdrant", Estado.OK, f"em {config.vetorial.url} — coleções: {detalhe}"))

        dimensao = servico.repositorio.dimensao_da_colecao()
        colecao = config.vetorial.colecao
        if dimensao is None:
            itens.append(
                Verificacao(
                    f"Coleção '{colecao}'",
                    Estado.AVISO,
                    "ainda não existe",
                    "Criada automaticamente pela etapa de indexação.",
                )
            )
        elif dimensao != config.embedding.dimensao:
            itens.append(
                Verificacao(
                    f"Coleção '{colecao}'",
                    Estado.FALHA,
                    f"vetores de {dimensao} dimensões, mas o modelo atual produz {config.embedding.dimensao}",
                    "Foi criada com outro modelo de embedding. Recrie a coleção ao indexar.",
                )
            )
        else:
            pontos = servico.repositorio.contar_pontos()
            itens.append(
                Verificacao(
                    f"Coleção '{colecao}'",
                    Estado.OK if pontos else Estado.AVISO,
                    f"{pontos} pontos indexados, {dimensao} dimensões",
                    "" if pontos else "Coleção vazia — rode a indexação.",
                )
            )

    # ── artefatos do pipeline ─────────────────────────────────────────────
    documentos = servico.contar_documentos()
    itens.append(
        Verificacao(
            "Corpus baixado",
            Estado.OK if documentos else Estado.AVISO,
            f"{documentos} arquivos .txt" if documentos else "pasta vazia",
            "" if documentos else "Rode a etapa de download do corpus.",
        )
    )

    if servico.chunks_existem():
        tamanho_mb = config.caminhos.chunks.stat().st_size / 1_048_576
        itens.append(Verificacao("Chunks gerados", Estado.OK, f"{tamanho_mb:.1f} MB"))
    else:
        itens.append(Verificacao("Chunks gerados", Estado.AVISO, "arquivo ausente", "Rode a etapa de chunking."))

    return itens


def pronto_para_perguntar(itens: list[Verificacao]) -> bool:
    """Se dá para responder pergunta agora: sem falha em nenhuma verificação."""
    return not any(item.estado is Estado.FALHA for item in itens)
