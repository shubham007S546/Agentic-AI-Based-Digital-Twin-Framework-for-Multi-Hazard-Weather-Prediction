"""Knowledge Engine package.

This package wraps the ingestion and knowledge management layer around the
existing RAG pipeline without replacing the embedding, retriever, or vector
store implementations.
"""

from .config.config import config
from .orchestrator import KnowledgeEngine

__all__ = ["config", "KnowledgeEngine"]
