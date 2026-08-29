"""
Configuração central do pipeline.

Antes cada script tinha suas próprias constantes no topo, e as mesmas quatro
(URL do Ollama, modelo de embedding, URL do Qdrant, nome da coleção) apareciam
repetidas em quatro arquivos — mudar a coleção exigia lembrar de todos. Aqui
elas existem uma vez só.

Os valores continuam sendo constantes no código, não `.env` nem argumento
obrigatório de linha de comando: o padrão vive aqui e é o que roda. A CLI e o
menu podem sobrescrever campos em memória para uma execução (`--k 8`, opção
"Configuração" do menu), sem gravar nada em disco.

As seções são `dataclass` aninhadas para que o menu possa listar e editar os
campos por introspecção (`dataclasses.fields`), em vez de ter um formulário
escrito à mão que envelhece a cada campo novo.
"""

from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, get_type_hints

# src/rag/config.py → parents[2] é a raiz do repositório. Os caminhos são
# resolvidos a partir daqui para que o diretório de onde o programa é chamado
# não influencie em nada.
RAIZ_PROJETO = Path(__file__).resolve().parents[2]


@dataclass
class ConfigCaminhos:
    """Onde vivem os artefatos gerados. Tudo abaixo de `data/`, tudo gitignored."""

    dados: Path = RAIZ_PROJETO / "data"

    @property
    def corpus(self) -> Path:
        return self.dados / "corpus_uesp"

    @property
    def chunks(self) -> Path:
        return self.dados / "chunks.jsonl"

    @property
    def qdrant_storage(self) -> Path:
        return self.dados / "qdrant_storage"


@dataclass
class ConfigDownload:
    """Coleta do corpus de teste na UESP (namespace Lore, via API MediaWiki)."""

    api_url: str = "https://en.uesp.net/w/api.php"
    namespace: str = "Lore"
    tamanho_minimo: int = 80  # caracteres — abaixo disso a página é vazia ou redirect
    candidatos: int = 50_000  # teto alto o bastante pro namespace inteiro
    titulos_por_lote: int = 50  # máximo aceito por requisição em prop=revisions
    lotes_paralelos: int = 8
    timeout: int = 30
    # A etiqueta de identificação é exigência de etiqueta das APIs MediaWiki;
    # sem ela a wiki pode limitar ou bloquear o cliente sem aviso.
    user_agent: str = "IA-Freiriana-RAG/2.0 (protótipo acadêmico; contato via repositório)"


@dataclass
class ConfigChunking:
    """Corte dos documentos em trechos."""

    estrategia: str = "paragrafo"  # ver rag.etapas.chunking.ESTRATEGIAS
    tamanho_minimo: int = 60  # caracteres — abaixo disso o trecho não se sustenta sozinho
    tamanho_maximo: int = 2000  # acima disso é página de lista/índice; subdivide


@dataclass
class ConfigEmbedding:
    """Geração de vetores. `dimensao` precisa bater com a saída do modelo."""

    ollama_url: str = "http://localhost:11434"
    modelo: str = "bge-m3"
    dimensao: int = 1024
    tamanho_lote: int = 16  # chunks por chamada ao Ollama
    lotes_paralelos: int = 4  # processamento local: paralelismo modesto
    timeout: int = 120


@dataclass
class ConfigVetorial:
    """Banco vetorial. `colecao` é o que muda ao trocar de corpus."""

    url: str = "http://localhost:6333"
    colecao: str = "uesp_lore"  # corpus real do IPF entraria como outra coleção
    timeout: int = 60


@dataclass
class ConfigBusca:
    """Recuperação."""

    k: int = 5  # trechos recuperados por pergunta
    score_minimo: float = 0.0  # 0 = sem corte; subir filtra ruído do topo da lista


@dataclass
class ConfigGeracao:
    """Geração da resposta final."""

    ollama_url: str = "http://localhost:11434"
    modelo: str = "qwen2.5:7b"
    temperatura: float = 0.2  # baixa: a resposta deve seguir os trechos, não improvisar
    timeout: int = 300
    streaming: bool = True  # imprime conforme gera, em vez de esperar o texto inteiro


@dataclass
class Config:
    """Configuração completa. Uma instância viaja por todas as etapas."""

    caminhos: ConfigCaminhos = field(default_factory=ConfigCaminhos)
    download: ConfigDownload = field(default_factory=ConfigDownload)
    chunking: ConfigChunking = field(default_factory=ConfigChunking)
    embedding: ConfigEmbedding = field(default_factory=ConfigEmbedding)
    vetorial: ConfigVetorial = field(default_factory=ConfigVetorial)
    busca: ConfigBusca = field(default_factory=ConfigBusca)
    geracao: ConfigGeracao = field(default_factory=ConfigGeracao)

    def secoes(self) -> dict[str, Any]:
        """Seções editáveis, por nome — usado pelo menu de configuração."""
        return {f.name: getattr(self, f.name) for f in fields(self) if f.name != "caminhos"}

    def campos_editaveis(self, secao: str) -> list[str]:
        return [f.name for f in fields(self.secoes()[secao])]

    def definir(self, secao: str, campo: str, valor: str) -> Any:
        """Atribui um campo convertendo o texto digitado para o tipo declarado.

        A conversão vem da anotação do campo, então um campo novo na dataclass
        já nasce editável pelo menu sem nenhuma alteração aqui.
        """
        alvo = self.secoes()[secao]
        tipo = get_type_hints(type(alvo))[campo]

        if tipo is bool:
            convertido: Any = valor.strip().lower() in {"1", "sim", "true", "s", "y"}
        else:
            convertido = tipo(valor)

        setattr(alvo, campo, convertido)
        return convertido


# Instância única usada pelo programa. A CLI e o menu ajustam campos dela em
# memória; nada é persistido — reiniciar volta aos padrões acima.
CONFIG = Config()
