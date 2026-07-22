import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from embeddings.embedding_model import EmbeddingModel
from vectorstore.faiss_db import FAISSVectorStore


class Retriever:

    def __init__(self):

        self.embedding_model = EmbeddingModel()

        self.vector_store = FAISSVectorStore()

        self.vector_store.load()

    def retrieve(
            self,
            query,
            top_k=4
    ):

        query_embedding = self.embedding_model.embed_text(
            query
        )

        results = self.vector_store.search(
            query_embedding,
            top_k
        )

        return results