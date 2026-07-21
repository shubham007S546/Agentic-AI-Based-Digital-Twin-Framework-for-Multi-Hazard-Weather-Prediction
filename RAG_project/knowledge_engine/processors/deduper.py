import hashlib
from typing import Dict, Iterable, List, Set


def compute_content_hash(text: str) -> str:
    normalized = text.strip().encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()


def dedupe_documents(documents: Iterable[Dict[str, object]]) -> List[Dict[str, object]]:
    seen: Set[str] = set()
    unique = []
    for document in documents:
        text = str(document.get("page_content", ""))
        content_hash = compute_content_hash(text)
        if content_hash in seen:
            continue
        seen.add(content_hash)
        document.setdefault("metadata", {})["content_hash"] = content_hash
        unique.append(document)
    return unique
