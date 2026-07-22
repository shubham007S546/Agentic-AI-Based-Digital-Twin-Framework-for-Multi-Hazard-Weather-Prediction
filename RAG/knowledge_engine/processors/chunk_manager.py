from pathlib import Path
from typing import List, Optional


class ChunkManager:
    def __init__(self):
        self.cleaner = None
        self.splitter = None

    def _ensure_components(self):
        if self.cleaner and self.splitter:
            return

        try:
            from RAG_project.preprocessing.chunk_cleaner import ChunkCleaner
            from RAG_project.chunking.text_splitter import TextSplitter
        except ImportError as exc:
            raise RuntimeError("Unable to import the existing RAG chunking pipeline.") from exc

        self.cleaner = ChunkCleaner()
        self.splitter = TextSplitter()

    def clean_documents(self, documents: List[object]) -> List[object]:
        self._ensure_components()
        return self.cleaner.clean_documents(documents)

    def split_documents(self, documents: List[object]) -> List[object]:
        self._ensure_components()
        return self.splitter.split_documents(documents)

    def filter_and_merge(self, chunks: List[object]) -> List[object]:
        self._ensure_components()
        return self.cleaner.filter_and_merge(chunks)
