from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .chunk_manager import ChunkManager
from .deduper import dedupe_documents
from .metadata_extractor import MetadataExtractor
from .normalizer import Normalizer


@dataclass
class ProcessingDocument:
    page_content: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class KnowledgePipeline:
    def __init__(self) -> None:
        self.normalizer = Normalizer()
        self.metadata_extractor = MetadataExtractor()
        self.chunk_manager = ChunkManager()

    def _ensure_processing_documents(self, documents: List[Any]) -> List[ProcessingDocument]:
        result: List[ProcessingDocument] = []
        for document in documents:
            if isinstance(document, ProcessingDocument):
                result.append(document)
                continue
            if isinstance(document, dict):
                text = str(document.get("page_content", ""))
                metadata = dict(document.get("metadata", {}))
                result.append(ProcessingDocument(page_content=text, metadata=metadata))
                continue
            if hasattr(document, "page_content") and hasattr(document, "metadata"):
                result.append(ProcessingDocument(page_content=document.page_content, metadata=dict(document.metadata)))
        return result

    def process(self, documents: List[Any]) -> List[Any]:
        if not documents:
            return []

        prepared = self._ensure_processing_documents(documents)
        text_documents = [ProcessingDocument(
            page_content=self.normalizer.normalize(doc.page_content),
            metadata=doc.metadata,
        ) for doc in prepared]

        unique_documents = dedupe_documents([
            {"page_content": doc.page_content, "metadata": doc.metadata} for doc in text_documents
        ])
        wrapped_documents = [ProcessingDocument(page_content=d["page_content"], metadata=d["metadata"]) for d in unique_documents]

        # Convert to the Document shape expected by the existing chunking pipeline.
        chunkable_documents = [self._wrap_for_chunking(doc) for doc in wrapped_documents]
        cleaned = self.chunk_manager.clean_documents(chunkable_documents)
        chunks = self.chunk_manager.split_documents(cleaned)
        chunks = self.chunk_manager.filter_and_merge(chunks)
        return chunks

    def _wrap_for_chunking(self, document: ProcessingDocument) -> Any:
        try:
            from RAG_project.loaders.pdf_loader import Document
        except Exception:
            @dataclass
            class DocumentWrapper:
                page_content: str
                metadata: Dict[str, Any]

            return DocumentWrapper(page_content=document.page_content, metadata=document.metadata)
        return Document(page_content=document.page_content, metadata=document.metadata)
