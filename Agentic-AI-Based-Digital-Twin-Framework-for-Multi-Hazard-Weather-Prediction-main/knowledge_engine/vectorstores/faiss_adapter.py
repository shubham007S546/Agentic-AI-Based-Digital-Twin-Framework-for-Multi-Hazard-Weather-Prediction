from typing import Any, Dict, Iterable, List, Optional

from .base import VectorStoreAdapter


class FaissAdapter(VectorStoreAdapter):
    def __init__(self, namespace: str = "default") -> None:
        self.namespace = namespace
        self.vector_db = None
        self._loaded = False

    def _ensure_vector_db(self) -> None:
        if self._loaded:
            return
        try:
            from RAG_project.vectorstore.faiss_db import FAISSVectorStore
        except ImportError as exc:
            raise RuntimeError("Unable to import the existing FAISS vector store implementation.") from exc
        self.vector_db = FAISSVectorStore()
        self._loaded = True

    def load(self) -> None:
        self._ensure_vector_db()
        try:
            self.vector_db.load()
        except Exception:
            # If the index does not exist yet, it's fine to start from scratch.
            pass

    def save(self) -> None:
        if not self.vector_db:
            return
        self.vector_db.save()

    def upsert(self, documents: Iterable[Any], embeddings: Any) -> None:
        self._ensure_vector_db()
        if self.vector_db.index is None or len(getattr(self.vector_db, "documents", [])) == 0:
            self.vector_db.build_index(embeddings, list(documents))
        else:
            self.vector_db.index.add(embeddings.astype("float32"))
            self.vector_db.documents.extend(list(documents))
        self.vector_db.save()

    def query(self, query_embedding: Any, top_k: int = 4) -> List[Any]:
        self._ensure_vector_db()
        return self.vector_db.search(query_embedding, top_k=top_k)

    def reset(self) -> None:
        self._ensure_vector_db()
        self.vector_db.index = None
        self.vector_db.documents = []
        self.save()
