"""
Embedding Model
---------------
Wraps SentenceTransformer with the handling a RAG pipeline actually needs:

  - GPU auto-detection (falls back to CPU cleanly, doesn't crash if no CUDA)
  - Batched encoding with a configurable batch size (encoding thousands of
    chunks one-by-one is slow and wastes GPU throughput)
  - L2-normalized embeddings — REQUIRED if your FAISS index uses inner
    product (IndexFlatIP) for cosine similarity; unnormalized vectors give
    wrong similarity rankings with that index type
  - Empty/whitespace-only text guarded against — encoding "" returns a
    valid but meaningless zero-ish vector that silently pollutes retrieval;
    this filters those out and tells you which documents got skipped
  - A separate embed_query() method — query embedding at inference time is
    conceptually different from bulk document embedding, and some
    sentence-transformer models expect different handling (E5 models need a
    "query: " prefix vs "passage: " prefix, for example) — kept as a hook
    even though the default model here doesn't need it, so upgrading the
    model later doesn't require touching every call site
"""
import sys
from pathlib import Path

# Safeguard against mismatched torchvision crashing sentence_transformers
if "torchvision" not in sys.modules:
    try:
        import torchvision
    except Exception:
        sys.modules["torchvision"] = None

_rag_root = str(Path(__file__).resolve().parent.parent)
if _rag_root in sys.path:
    sys.path.remove(_rag_root)
sys.path.insert(0, _rag_root)

import numpy as np
from sentence_transformers import SentenceTransformer

from config import EMBEDDING_MODEL
from utils.logger import logger


# -------------------------------
# Tunable knobs
# -------------------------------
BATCH_SIZE = 64
NORMALIZE_EMBEDDINGS = True   # keep True unless your vectorstore uses raw L2 distance


class EmbeddingModel:

    def __init__(self, model_name: str = EMBEDDING_MODEL, batch_size: int = BATCH_SIZE):
        self.model_name = model_name
        self.batch_size = batch_size

        device = self._detect_device()

        logger.info(f"Loading embedding model '{model_name}' on device: {device}")
        try:
            self.model = SentenceTransformer(model_name, device=device)
        except Exception as e:
            logger.error(f"Failed to load embedding model '{model_name}': {e}")
            raise

        self.embedding_dim = self.model.get_sentence_embedding_dimension()
        logger.info(f"Embedding model ready. Dimension: {self.embedding_dim}")

    def _detect_device(self) -> str:
        try:
            import torch
            if torch.cuda.is_available():
                return "cuda"
        except ImportError:
            pass
        return "cpu"

    # ---------------------------------------------------------
    # Single text -> single vector (queries at inference time)
    # ---------------------------------------------------------
    def embed_query(self, text: str) -> np.ndarray:
        if not text or not text.strip():
            raise ValueError("embed_query received empty text — cannot embed nothing.")

        embedding = self.model.encode(
            text,
            convert_to_numpy=True,
            normalize_embeddings=NORMALIZE_EMBEDDINGS,
        )
        return embedding

    # ---------------------------------------------------------
    # Raw text list -> vectors (lower-level, used by embed_documents)
    # ---------------------------------------------------------
    def embed_text(self, texts, show_progress_bar: bool = False) -> np.ndarray:
        if isinstance(texts, str):
            texts = [texts]

        embeddings = self.model.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=NORMALIZE_EMBEDDINGS,
            batch_size=self.batch_size,
            show_progress_bar=show_progress_bar,
        )
        return embeddings

    # ---------------------------------------------------------
    # Document objects -> vectors, with empty-text filtering
    # ---------------------------------------------------------
    def embed_documents(self, documents):
        """
        Returns (valid_documents, embeddings) — a filtered document list
        paired 1:1 with the embeddings array. Returning the filtered list
        alongside the embeddings (rather than just the embeddings) matters:
        if any documents get skipped for being empty, the caller needs to
        know which documents survived so metadata/indexing stays aligned.
        """
        valid_documents = []
        texts = []
        skipped = 0

        for doc in documents:
            if doc.page_content and doc.page_content.strip():
                valid_documents.append(doc)
                texts.append(doc.page_content)
            else:
                skipped += 1

        if skipped:
            logger.warning(f"Skipped {skipped} document(s) with empty/whitespace-only content during embedding.")

        if not texts:
            logger.error("No valid documents to embed — all were empty.")
            return [], np.empty((0, self.embedding_dim))

        logger.info(f"Embedding {len(texts)} documents (batch_size={self.batch_size})")

        embeddings = self.model.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=NORMALIZE_EMBEDDINGS,
            batch_size=self.batch_size,
            show_progress_bar=True,
        )

        logger.info(f"Embedding complete. Shape: {embeddings.shape}")

        return valid_documents, embeddings