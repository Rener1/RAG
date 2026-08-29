"""
Exceções do domínio.

Existem para que a interface possa distinguir "o serviço está fora do ar"
(recuperável, com instrução de conserto) de "o código quebrou" (bug), em vez
de mostrar um traceback cru pro usuário em qualquer um dos dois casos.
"""


class ErroPipeline(Exception):
    """Base de tudo que o pipeline sabe explicar ao usuário.

    `sugestao` carrega o comando ou passo que resolve o problema — a interface
    imprime junto com a mensagem.
    """

    def __init__(self, mensagem: str, sugestao: str = "") -> None:
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.sugestao = sugestao


class ErroConexao(ErroPipeline):
    """Serviço externo (Ollama, Qdrant, API da wiki) inacessível."""


class ErroConfiguracao(ErroPipeline):
    """Configuração inconsistente — detectada antes de gastar processamento."""


class ErroDimensaoIncompativel(ErroConfiguracao):
    """A coleção existente foi criada com outro modelo de embedding.

    Detectar isso na hora de indexar evita o modo de falha antigo: a coleção
    era reaproveitada em silêncio e só estourava lotes adiante, com erro de
    dimensão vindo do servidor e nenhuma pista da causa.
    """


class ErroPreRequisito(ErroPipeline):
    """Falta o artefato produzido pela etapa anterior."""


class ErroMarcoInvalido(ErroConfiguracao):
    """O marco pedagógico ativo não pôde ser lido.

    É erro, e não queda silenciosa para o prompt genérico, de propósito: o marco
    é o que diferencia este sistema de "um chatbot com um prompt bonito", e
    perdê-lo sem aviso seria perder exatamente isso sem ninguém notar.
    """
