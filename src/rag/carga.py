"""
Limitador de carga — o equivalente, para o pipeline, a um limitador de quadros.

O objetivo é **poupar o hardware**, não liberar a máquina para outra tarefa. E
isso não se faz baixando o clock por fora (power cap, perfil da placa): é o app
que consome menos, e o governador de energia da própria GPU responde baixando
clock e tensão.

A forma importa mais que a intenção. Medido na RX 9070 XT, embutindo recortes
reais e lendo clock, potência e temperatura pelo sysfs (2026-10-05):

    sem limite (4 × lote 16)        38,8k ch/s · 3000 MHz · 298 W, picos 352 · junção 74–79 °C
    rajada 5 s + descanso 5 s       23,0k ch/s · alterna 1237↔3038 MHz · picos 338 W · junção 48↔77 °C
    teto de vazão 20k ch/s          19,9k ch/s · 1603 MHz · picos 287 W · junção 49–72 °C
    fração 75 %, lote 8             15,9k ch/s · 1568 MHz ·  90 W, picos 112 · junção 48–55 °C
    fração 50 %, lote 8             10,9k ch/s · 1232 MHz ·  51 W, picos 184 · junção 46–57 °C

Três leituras:

- **Descanso longo é ciclo térmico.** Em rajadas de segundos a placa trabalha no
  clock máximo e esfria entre uma e outra — aquece e esfria o tempo todo, que é o
  que fadiga solda. Média baixa, estresse alto.
- **Descanso fino baixa o clock.** Pausando uma fração de segundo depois de cada
  lote, o governador enxerga uso parcial e reduz clock e tensão; a temperatura se
  acomoda num patamar baixo e estável. É o "meio clock" sem tocar na placa — e
  gasta menos energia por caractere (4,8 contra 7,5 J por mil caracteres).
- **Teto de vazão briga com o governador.** Quando o clock baixa, a vazão cai
  abaixo do alvo, o limitador para de descansar para alcançá-lo, e a placa volta
  aos picos. Por isso o controle é por fração do tempo, não por caracteres/s.

O limitador é **um só para o processo inteiro**, compartilhado por embutidor,
reordenador e gerador de apoio, e serializa o trabalho que passa por ele. Uma
pausa por thread não funciona: com quatro workers a 50 % cada, o descanso de um
coincide com o trabalho dos outros e a GPU fica ocupada quase o tempo todo.

**Em aberto:** numa indexação real de 64 min, a placa ficou em ~80 W nos
primeiros 25 min e depois subiu para 200–250 W, com o limitador cumprindo a
proporção. Não reproduziu em execução curta. Ver `docs/estado-do-desenvolvimento.md`.

Mora na raiz do pacote porque embrulha peças pelos protocolos — as etapas
recebem o embutidor limitado sem saber que ele é limitado, e nenhuma muda.
"""

import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from .erros import ErroConfiguracao
from .modelos import TrechoRecuperado


class LimitadorDeCarga:
    """Depois de cada trabalho de duração `d`, descansa `d × (1/fração − 1)`.

    Com fração 0,75, um lote de 0,3 s ganha 0,1 s de pausa; com 0,5, ganha 0,3 s.
    O descanso acontece **segurando o lock**, então nenhum outro trabalho começa
    durante a pausa — é o que torna a fração global e não por thread.
    """

    def __init__(
        self,
        fracao: float,
        *,
        relogio: Callable[[], float] = time.monotonic,
        dormir: Callable[[float], None] = time.sleep,
    ) -> None:
        if not 0 < fracao <= 1:
            raise ErroConfiguracao(
                f"carga.fracao precisa estar entre 0 (exclusivo) e 1, e é {fracao}.",
                sugestao="Use 1 para sem limite, 0.75 para poupar a placa sem perder muito, 0.5 para poupar mais.",
            )
        self.fracao = fracao
        self._relogio = relogio
        self._dormir = dormir
        self._trava = threading.Lock()
        self.ocupado = 0.0  # segundos somados de trabalho, para relatório e teste
        self.descansado = 0.0

    @contextmanager
    def ocupar(self) -> Iterator[None]:
        """Envolve uma unidade de trabalho — um lote, uma reordenação, uma chamada."""
        with self._trava:
            inicio = self._relogio()
            try:
                yield
            finally:
                duracao = self._relogio() - inicio
                pausa = duracao * (1 / self.fracao - 1)
                self.ocupado += duracao
                if pausa > 0:
                    self.descansado += pausa
                    self._dormir(pausa)


class _Limitado:
    """Base dos invólucros: o que não é limitado passa direto à peça embrulhada.

    `dimensao`, `modelo`, `esta_disponivel` e o resto continuam respondendo como
    antes — o invólucro só interfere no método que de fato custa processamento.
    """

    def __init__(self, peca, limitador: LimitadorDeCarga) -> None:
        self._peca = peca
        self._limitador = limitador

    def __getattr__(self, nome: str):
        return getattr(self._peca, nome)


class EmbutidorLimitado(_Limitado):
    """Embutidor cujo `embutir` passa pelo limitador. Cobre indexação e busca."""

    @property
    def dimensao(self) -> int:
        return self._peca.dimensao

    def embutir(self, textos: list[str]) -> list[list[float]]:
        with self._limitador.ocupar():
            return self._peca.embutir(textos)


class ReordenadorLimitado(_Limitado):
    """Cross-encoder limitado — roda na GPU via torch, fora do Ollama."""

    def reordenar(self, pergunta: str, trechos: list[TrechoRecuperado]) -> list[TrechoRecuperado]:
        with self._limitador.ocupar():
            return self._peca.reordenar(pergunta, trechos)


class GeradorLimitado(_Limitado):
    """Gerador limitado. **Só para chamadas curtas e não interativas.**

    Consome a resposta inteira dentro do limitador e só então a entrega: o
    descanso precisa vir depois do trabalho, e o trabalho só termina quando o
    modelo para de gerar. Serve à triagem e à mediação, que querem a resposta
    inteira de qualquer jeito. A resposta final em streaming não passa por aqui:
    é uma rajada só por pergunta, e descansar depois dela não poupa nada.
    """

    def gerar(self, prompt: str) -> Iterator[str]:
        with self._limitador.ocupar():
            pedacos = list(self._peca.gerar(prompt))
        yield from pedacos
