import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List


def safe_document_id(source_path: str, max_length: int = 64) -> str:
    """Generate a safe, deterministic document identifier for filesystem storage.

    Replaces invalid Windows filename characters, normalizes path separators,
    truncates long names, and appends a short SHA256 hash.
    """
    normalized = str(source_path).replace("\\", "/")
    sanitized = re.sub(r"[<>:\\"/\\|?*]+", "_", normalized)
    sanitized = re.sub(r"_+", "_", sanitized).strip("_")
    if not sanitized:
        sanitized = "doc"
    hash_suffix = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]
    max_base_len = max_length - len(hash_suffix) - 1
    if len(sanitized) > max_base_len:
        sanitized = sanitized[:max_base_len].rstrip("_")
    return f"{sanitized}_{hash_suffix}"


class KnowledgeStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def persist_document(self, metadata: Dict[str, Any], raw_text: str, chunks: List[Any]) -> Path:
        collection = metadata.get("collection") or "processed"
        doc_id = metadata.get("doc_id") or metadata.get("source", "unknown")
        safe_id = safe_document_id(doc_id)
        collection_dir = self.root / collection
        document_dir = collection_dir / safe_id
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
