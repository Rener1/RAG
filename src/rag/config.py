"""
Configuração central do pipeline.

Antes cada script tinha suas próprias constantes no topo, e as mesmas quatro
(URL do Ollama, modelo de embedding, URL do Qdrant, nome da coleção) apareciam
repetidas em quatro arquivos — mudar a coleção exigia lembrar de todos. Aqui
elas existem uma vez só.

Os padrões continuam sendo constantes no código, não `.env`: o que está escrito
nas dataclasses abaixo é o que roda numa instalação limpa. Por cima deles entra
uma camada de sobreposição opcional, `config.toml`, e por cima dela as flags de
linha de comando e o menu:

    padrões daqui  →  config.toml (se existir)  →  flags de CLI / menu

O arquivo guarda **apenas o que difere do padrão**. É o que faz um campo novo
numa dataclass nascer funcionando sem migração, e o que faz apagar o arquivo
devolver o sistema ao comportamento documentado.

As seções são `dataclass` aninhadas para que o menu possa listar e editar os
campos por introspecção (`dataclasses.fields`), em vez de ter um formulário
escrito à mão que envelhece a cada campo novo. A persistência usa a mesma
introspecção, pelo mesmo motivo.
"""

import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, get_type_hints

from .erros import ErroConfiguracao

# src/rag/config.py → parents[2] é a raiz do repositório. Os caminhos são
# resolvidos a partir daqui para que o diretório de onde o programa é chamado
# não influencie em nada.
RAIZ_PROJETO = Path(__file__).resolve().parents[2]

CAMINHO_PADRAO_DA_CONFIGURACAO = RAIZ_PROJETO / "config.toml"


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

    @property
    def marcos(self) -> Path:
        """Marcos pedagógicos. Fora de `data/`: são versionados no git."""
        return RAIZ_PROJETO / "marcos"


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
class ConfigIntermediacao:
    """Reformulação e decomposição da pergunta antes da busca.

    Custa uma chamada ao modelo de geração e N buscas vetoriais por pergunta.
    `ligada = false` volta à busca direta, que é o caminho para medir `recall@k`
    sem o custo.
    """

    ligada: bool = True
    maximo_de_subconsultas: int = 3
    k_por_subconsulta: int = 8
    constante_rrf: int = 60
    incluir_pergunta_original: bool = True
    minimo_de_caracteres: int = 25  # abaixo disso, reformular não paga a chamada
    diversidade_por_documento: int = 0  # 0 = sem teto por documento


@dataclass
class ConfigSessao:
    """Diálogo multi-turno — problematizar antes de responder.

    A triagem decide quando entra: dúvida factual vai direto à busca. Quem
    pergunta pula com uma linha vazia, e `perguntar --direto` desliga de vez
    para esta execução. O marco pode desligar a problematização declarando
    `problematizar: não`, mas não pode ligá-la contra a configuração.
    """

    problematizar: bool = True
    classificar_com_modelo: bool = True
    perguntas_ancoradas: bool = True  # busca prévia para as perguntas não saírem genéricas
    maximo_de_rodadas: int = 1
    maximo_de_perguntas: int = 3


@dataclass
class ConfigMarco:
    """Marco pedagógico. O conteúdo mora em `marcos/*.md`, versionado no git."""

    ativo: str = "generico"  # "" desliga o marco e volta ao prompt genérico


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
    intermediacao: ConfigIntermediacao = field(default_factory=ConfigIntermediacao)
    sessao: ConfigSessao = field(default_factory=ConfigSessao)
    marco: ConfigMarco = field(default_factory=ConfigMarco)

    def secoes(self) -> dict[str, Any]:
        """Seções editáveis, por nome — usado pelo menu e pela persistência."""
        return {f.name: getattr(self, f.name) for f in fields(self)}

    def campos_editaveis(self, secao: str) -> list[str]:
        """Só os campos declarados. As propriedades derivadas ficam de fora."""
        return [f.name for f in fields(self.secoes()[secao])]

    def definir(self, secao: str, campo: str, valor: Any) -> Any:
        """Atribui um campo convertendo o valor para o tipo declarado.

        A conversão vem da anotação do campo, então um campo novo na dataclass
        já nasce editável pelo menu e persistível sem nenhuma alteração aqui.
        Aceita texto (do menu e da CLI) e valores já tipados (do TOML).
        """
        alvo = self.secoes()[secao]
        tipo = get_type_hints(type(alvo))[campo]

        setattr(alvo, campo, converter(valor, tipo, f"{secao}.{campo}"))
        return getattr(alvo, campo)


def converter(valor: Any, tipo: type, rotulo: str) -> Any:
    """Converte um valor para o tipo anotado do campo, ou explica por que não deu.

    `rotulo` é 'secao.campo' e entra na mensagem de erro: um TOML escrito à mão
    erra o tipo com frequência, e "não deu" sem dizer onde é inútil.
    """
    if tipo is bool:
        if isinstance(valor, bool):
            return valor
        if isinstance(valor, str):
            return valor.strip().lower() in {"1", "sim", "true", "s", "y"}
        raise ErroConfiguracao(
            f"{rotulo} espera verdadeiro ou falso, e recebeu {valor!r}.",
            sugestao="Use true ou false (sem aspas).",
        )

    # bool é subclasse de int em Python: sem esta guarda, `k = true` viraria 1.
    if isinstance(valor, bool):
        raise ErroConfiguracao(
            f"{rotulo} espera {tipo.__name__}, e recebeu um valor booleano.",
            sugestao=f"Escreva um valor do tipo {tipo.__name__}.",
        )

    try:
        return tipo(valor)
    except (TypeError, ValueError) as erro:
        raise ErroConfiguracao(
            f"{rotulo} espera {tipo.__name__}, e recebeu {valor!r}.",
            sugestao=f"Corrija o valor para um {tipo.__name__} válido ({erro}).",
        ) from erro


# ── persistência ──────────────────────────────────────────────────────────


@dataclass
class ConfiguracaoCarregada:
    """A configuração em vigor mais a procedência de cada valor.

    Guardar `do_arquivo` é o que permite ao comando `config` dizer de onde cada
    valor veio — a pergunta que mais aparece quando o mesmo comando se comporta
    diferente em duas máquinas.
    """

    config: Config
    caminho: Path | None = None  # None = nenhum arquivo foi lido
    do_arquivo: dict[str, dict[str, Any]] = field(default_factory=dict)
    avisos: list[str] = field(default_factory=list)


def diferencas(config: Config) -> dict[str, dict[str, Any]]:
    """Só os campos que diferem do padrão — é o que vai para o arquivo."""
    padrao = Config()
    resultado: dict[str, dict[str, Any]] = {}

    for nome_secao, secao in config.secoes().items():
        secao_padrao = padrao.secoes()[nome_secao]
        mudados = {
            campo: getattr(secao, campo)
            for campo in config.campos_editaveis(nome_secao)
            if getattr(secao, campo) != getattr(secao_padrao, campo)
        }
        if mudados:
            resultado[nome_secao] = mudados

    return resultado


def aplicar(config: Config, valores: dict[str, Any], origem: str = "") -> list[str]:
    """Aplica valores lidos de um arquivo. Devolve os avisos.

    Chave desconhecida vira aviso, não erro: um arquivo escrito para uma versão
    anterior não pode impedir o programa de subir. Tipo incompatível, sim, é
    erro — ali o usuário quis dizer algo e o programa entenderia errado.
    """
    avisos: list[str] = []
    onde = f" em {origem}" if origem else ""
    secoes = config.secoes()

    for nome_secao, campos in valores.items():
        if nome_secao not in secoes:
            avisos.append(f"seção desconhecida '{nome_secao}'{onde} — ignorada.")
            continue
        if not isinstance(campos, dict):
            avisos.append(f"'{nome_secao}'{onde} não é uma seção — ignorada.")
            continue

        editaveis = config.campos_editaveis(nome_secao)
        for campo, valor in campos.items():
            if campo not in editaveis:
                avisos.append(f"campo desconhecido '{nome_secao}.{campo}'{onde} — ignorado.")
                continue
            config.definir(nome_secao, campo, valor)

    return avisos


def ler(caminho: Path) -> dict[str, Any]:
    """Lê o TOML. Arquivo ausente devolve vazio; TOML inválido é erro explicado."""
    if not caminho.exists():
        return {}

    try:
        with caminho.open("rb") as arquivo:
            return tomllib.load(arquivo)
    except tomllib.TOMLDecodeError as erro:
        raise ErroConfiguracao(
            f"{caminho} não é um TOML válido: {erro}",
            sugestao="Corrija a sintaxe do arquivo, ou rode com --sem-config para ignorá-lo.",
        ) from erro


def carregar(caminho: Path | None = None, *, usar_arquivo: bool = True) -> ConfiguracaoCarregada:
    """Configuração com o arquivo aplicado sobre os padrões.

    Arquivo ausente não é erro: devolve os padrões. `usar_arquivo=False` é o que
    `--sem-config` usa para reproduzir o comportamento de uma instalação limpa.
    """
    config = Config()
    if not usar_arquivo:
        return ConfiguracaoCarregada(config)

    alvo = caminho or CAMINHO_PADRAO_DA_CONFIGURACAO
    valores = ler(alvo)
    avisos = aplicar(config, valores, origem=alvo.name)

    # Só o que foi de fato aplicado conta como procedência do arquivo.
    aplicados = {
        secao: {
            campo: getattr(config.secoes()[secao], campo) for campo in campos if campo in config.campos_editaveis(secao)
        }
        for secao, campos in valores.items()
        if secao in config.secoes() and isinstance(campos, dict)
    }

    return ConfiguracaoCarregada(
        config=config,
        caminho=alvo if valores else None,
        do_arquivo={s: c for s, c in aplicados.items() if c},
        avisos=avisos,
    )


def origem_dos_valores(carregada: ConfiguracaoCarregada) -> dict[tuple[str, str], str]:
    """(secao, campo) → 'padrão' | 'arquivo' | 'flag'."""
    padrao = Config()
    config = carregada.config
    origens: dict[tuple[str, str], str] = {}

    for nome_secao, secao in config.secoes().items():
        do_arquivo = carregada.do_arquivo.get(nome_secao, {})
        secao_padrao = padrao.secoes()[nome_secao]

        for campo in config.campos_editaveis(nome_secao):
            atual = getattr(secao, campo)
            if campo in do_arquivo and atual == do_arquivo[campo]:
                origens[(nome_secao, campo)] = "arquivo"
            elif atual != getattr(secao_padrao, campo):
                origens[(nome_secao, campo)] = "flag"
            else:
                origens[(nome_secao, campo)] = "padrão"

    return origens


def formatar_valor_toml(valor: Any) -> str:
    if isinstance(valor, bool):
        return "true" if valor else "false"
    if isinstance(valor, (int, float)):
        return repr(valor)

    texto = str(valor).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{texto}"'


def escrever_toml(valores: dict[str, dict[str, Any]]) -> str:
    """Serializa as seções. Só escalares — é tudo o que a configuração tem."""
    linhas = [
        "# config.toml — sobreposição aos padrões de src/rag/config.py.",
        "# Só o que difere do padrão fica aqui; apagar este arquivo volta ao padrão.",
        "# Gerado por `python3 main.py config --salvar` (comentários seus se perdem ao regravar).",
    ]

    for nome_secao, campos in valores.items():
        linhas.append("")
        linhas.append(f"[{nome_secao}]")
        linhas.extend(f"{campo} = {formatar_valor_toml(valor)}" for campo, valor in campos.items())

    return "\n".join(linhas) + "\n"


CABECALHO_DO_EXEMPLO = """\
# config.exemplo.toml — modelo para o config.toml desta máquina.
#
# Copie para `config.toml` e descomente só o que precisar mudar:
#
#     cp config.exemplo.toml config.toml
#
# Tudo aqui está com o valor padrão do código, então um arquivo com todas as
# linhas comentadas equivale a não ter arquivo nenhum. A precedência é
# padrões de src/rag/config.py → config.toml → flags da linha de comando.
#
# `python3 main.py config` mostra o que está em vigor e de onde cada valor veio.
# `python3 main.py config --salvar` grava aqui do lado, em config.toml, o que
# você ajustou pelo menu ou por flag. `--sem-config` ignora o arquivo.
#
# Este arquivo é gerado a partir das dataclasses de src/rag/config.py. Para
# regerá-lo depois de acrescentar um campo:
#
#     python3 -c "import sys; sys.path.insert(0,'src'); from rag.config import escrever_exemplo; escrever_exemplo()"
"""

# Valor a mostrar no exemplo quando o padrão é um caminho absoluto desta máquina.
EXEMPLOS_DE_CAMINHO = {("caminhos", "dados"): '"data"   # padrão: a pasta data/ na raiz do repositório'}


def texto_de_exemplo() -> str:
    """O `config.exemplo.toml`, gerado das dataclasses para nunca envelhecer."""
    config = Config()
    linhas = [CABECALHO_DO_EXEMPLO.rstrip("\n")]

    for nome_secao, secao in config.secoes().items():
        doc = (type(secao).__doc__ or "").strip().split("\n")[0]
        linhas.extend(["", f"# {doc}", f"[{nome_secao}]"])
        for campo in config.campos_editaveis(nome_secao):
            mostrado = EXEMPLOS_DE_CAMINHO.get((nome_secao, campo)) or formatar_valor_toml(getattr(secao, campo))
            linhas.append(f"# {campo} = {mostrado}")

    return "\n".join(linhas) + "\n"


def escrever_exemplo(caminho: Path | None = None) -> Path:
    alvo = caminho or RAIZ_PROJETO / "config.exemplo.toml"
    alvo.write_text(texto_de_exemplo(), encoding="utf-8")
    return alvo


def salvar(config: Config, caminho: Path | None = None) -> Path:
    """Grava as diferenças em relação ao padrão. Só quando pedido explicitamente."""
    alvo = caminho or CAMINHO_PADRAO_DA_CONFIGURACAO
    alvo.parent.mkdir(parents=True, exist_ok=True)
    alvo.write_text(escrever_toml(diferencas(config)), encoding="utf-8")
    return alvo


# Instância com os padrões do código, sem nenhuma sobreposição. Serve de
# referência para `diferencas()` e de fallback para quem constrói um `Servico`
# sem passar configuração (testes, principalmente).
CONFIG = Config()
