from typing import Dict, List

CORE_METADATA_FIELDS: List[str] = [
    "doc_id",
    "title",
    "organization",
    "district",
    "hazard",
    "language",
    "publication_date",
    "authors",
    "page",
    "document_type",
    "source",
    "url",
    "content_hash",
    "file_path",
    "collection",
    "source_type",
]


def normalize_metadata(metadata: Dict[str, object]) -> Dict[str, object]:
    normalized = {k: v for k, v in metadata.items() if v is not None}
    for field in CORE_METADATA_FIELDS:
        if field not in normalized:
            normalized[field] = None
    return normalized
