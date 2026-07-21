"""
Singleton Accessors
--------------------
Expensive resources (SentenceTransformer, CrossEncoder, Gemini LLM,
FAISS index) must be loaded exactly ONCE per process and reused
everywhere instead of being re-instantiated by every class that needs
them (Retriever, HybridRetriever, QueryRewriter, RAGChain, etc.).

Uses functools.lru_cache(maxsize=1) as a simple, thread-safe-enough
singleton for a single-process CLI/app. Every other module should
import the getter functions below instead of constructing these
classes directly.

NOTE: This assumes your EmbeddingModel / Reranker / GeminiLLM /
FAISSVectorStore classes take no required constructor args beyond
what they already read from config. Adjust the constructor calls
below if your actual classes differ.
"""

from functools import lru_cache

from embeddings.embedding_model import EmbeddingModel
from retriever.reranker import Reranker
from llm.llm import GroqLLM
from vectorstore.faiss_db import FAISSVectorStore


@lru_cache(maxsize=1)
def get_embedding_model() -> EmbeddingModel:
    """SentenceTransformer wrapper — loaded once, reused for every
    query embedding (and for the one-time corpus embedding in
    build_index.py)."""
    return EmbeddingModel()


@lru_cache(maxsize=1)
def get_reranker() -> Reranker:
    """CrossEncoder reranker — loaded once, reused by HybridRetriever."""
    return Reranker()


@lru_cache(maxsize=1)
def get_llm() -> GroqLLM:
    """Groq client — loaded once, reused by RAGChain and QueryRewriter."""
    return GroqLLM()


@lru_cache(maxsize=1)
def get_faiss_store() -> FAISSVectorStore:
    """Loads the persisted FAISS index from disk exactly once.

    ASSUMPTION: FAISSVectorStore exposes a `.load()` method mirroring
    its existing `.save()`. If it doesn't yet, add one — see the note
    left for vectorstore/faiss_db.py.
    """
    store = FAISSVectorStore()
    store.load()
    return store