"""Adaptadores dos serviços externos: Ollama, Qdrant e a wiki de origem do corpus."""

from .ollama import ClienteOllama, GeradorOllama
from .qdrant import RepositorioQdrant
from .uesp import ColetorUESP

__all__ = ["ClienteOllama", "ColetorUESP", "GeradorOllama", "RepositorioQdrant"]
