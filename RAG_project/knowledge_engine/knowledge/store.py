import json
from pathlib import Path
from typing import Any, Dict, List


class KnowledgeStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def persist_document(self, metadata: Dict[str, Any], raw_text: str, chunks: List[Any]) -> Path:
        collection = metadata.get("collection") or "processed"
        doc_id = metadata.get("doc_id") or metadata.get("source", "unknown")
        collection_dir = self.root / collection
        document_dir = collection_dir / doc_id
        document_dir.mkdir(parents=True, exist_ok=True)

        (document_dir / "document.txt").write_text(raw_text, encoding="utf-8")
        (document_dir / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")

        chunks_data = []
        for chunk in chunks:
            if hasattr(chunk, "page_content") and hasattr(chunk, "metadata"):
                chunks_data.append({
                    "page_content": chunk.page_content,
                    "metadata": self._clean_metadata(chunk.metadata),
                })
            elif isinstance(chunk, dict):
                chunks_data.append({
                    "page_content": chunk.get("page_content", ""),
                    "metadata": self._clean_metadata(chunk.get("metadata", {})),
                })
        (document_dir / "chunks.json").write_text(json.dumps(chunks_data, indent=2, ensure_ascii=False), encoding="utf-8")
        return document_dir

    def _clean_metadata(self, metadata: Any) -> Dict[str, Any]:
        if isinstance(metadata, dict):
            return {k: str(v) if not isinstance(v, (str, int, float, bool, type(None))) else v for k, v in metadata.items()}
        return {"metadata": str(metadata)}
