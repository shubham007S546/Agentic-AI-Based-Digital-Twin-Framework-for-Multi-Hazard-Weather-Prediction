from abc import ABC, abstractmethod
from typing import Any, Dict, Iterable, List, Optional


class VectorStoreAdapter(ABC):
    @abstractmethod
    def load(self) -> None:
        pass

    @abstractmethod
    def save(self) -> None:
        pass

    @abstractmethod
    def upsert(self, documents: Iterable[Any], embeddings: Any) -> None:
        pass

    @abstractmethod
    def query(self, query_embedding: Any, top_k: int = 4) -> List[Any]:
        pass

    @abstractmethod
    def reset(self) -> None:
        pass
