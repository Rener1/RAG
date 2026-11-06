"""
Grava planilha `.xlsx` pelo `openpyxl` — o único módulo que o importa.

Genérico de propósito: recebe abas já montadas (nome, colunas, linhas) e só
cuida da forma — cabeçalho fixo, filtro, largura, quebra de texto e a cor de
cada célula cujo valor esteja em `cores`. O que vai em cada aba é decidido em
`qualidade_ocr.py` e na ação do relatório.
"""

from dataclasses import dataclass, field
from pathlib import Path

from ..erros import ErroConfiguracao


@dataclass
class Aba:
    nome: str
    colunas: list[str]
    linhas: list[list]
    larguras: dict[str, int] = field(default_factory=dict)  # coluna → largura em caracteres
    cores: dict[str, str] = field(default_factory=dict)  # valor da célula → cor de fundo (RRGGBB)
    formatos: dict[str, str] = field(default_factory=dict)  # coluna → formato de número ("0.0%")
    com_filtro: bool = True


def gravar_planilha(destino: Path, abas: list[Aba]) -> Path:
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter
    except ImportError as erro:
        raise ErroConfiguracao("O `openpyxl` não está instalado.", "pip3 install -r requirements.txt") from erro

    livro = Workbook()
    livro.remove(livro.active)
    for aba in abas:
        folha = livro.create_sheet(aba.nome[:31])
        folha.append(aba.colunas)
        for celula in folha[1]:
            celula.font = Font(bold=True)
            celula.alignment = Alignment(vertical="top", wrap_text=True)
        preenchimentos = {v: PatternFill("solid", start_color=c, end_color=c) for v, c in aba.cores.items()}
        formatos = {i: aba.formatos[nome] for i, nome in enumerate(aba.colunas) if nome in aba.formatos}
        for linha in aba.linhas:
            folha.append(["" if v is None else v for v in linha])
            for indice, celula in enumerate(folha[folha.max_row]):
                celula.alignment = Alignment(vertical="top", wrap_text=True)
                if isinstance(celula.value, str) and celula.value in preenchimentos:
                    celula.fill = preenchimentos[celula.value]
                if indice in formatos and isinstance(celula.value, (int, float)):
                    celula.number_format = formatos[indice]
        for indice, nome in enumerate(aba.colunas, start=1):
            folha.column_dimensions[get_column_letter(indice)].width = aba.larguras.get(nome, max(10, len(nome) + 2))
        folha.freeze_panes = "A2"
        if aba.com_filtro and aba.linhas:
            folha.auto_filter.ref = folha.dimensions
    destino.parent.mkdir(parents=True, exist_ok=True)
    livro.save(destino)
    return destino
