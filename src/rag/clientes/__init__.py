"""Adaptadores dos serviços externos: Ollama, Qdrant, a wiki de origem do corpus e as ferramentas de PDF."""

from .ollama import ClienteOllama, GeradorOllama
from .pdf import LeitorPoppler, MotorKraken, MotorOcrmypdf, MotorTesseract, ReconhecedorOcrmypdf
from .qdrant import RepositorioQdrant
from .reordenador import ReordenadorLocal
from .uesp import ColetorUESP

__all__ = [
    "ClienteOllama",
    "ColetorUESP",
    "GeradorOllama",
    "LeitorPoppler",
    "MotorKraken",
    "MotorOcrmypdf",
    "MotorTesseract",
    "ReconhecedorOcrmypdf",
    "ReordenadorLocal",
    "RepositorioQdrant",
]
