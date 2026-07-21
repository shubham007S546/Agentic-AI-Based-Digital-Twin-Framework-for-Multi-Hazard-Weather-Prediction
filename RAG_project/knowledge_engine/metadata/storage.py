import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .schema import normalize_metadata


class MetadataStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                doc_id TEXT PRIMARY KEY,
                source TEXT,
                source_type TEXT,
                collection TEXT,
                title TEXT,
                organization TEXT,
                district TEXT,
                hazard TEXT,
                language TEXT,
                publication_date TEXT,
                authors TEXT,
                page INTEGER,
                document_type TEXT,
                url TEXT,
                content_hash TEXT,
                file_path TEXT,
                chunk_count INTEGER,
                embedding_count INTEGER,
                status TEXT,
                error TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        self.conn.commit()

    def upsert_document(self, metadata: Dict[str, Any]) -> None:
        normalized = normalize_metadata(metadata)
        now = datetime.utcnow().isoformat()
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO documents (
                doc_id, source, source_type, collection, title, organization,
                district, hazard, language, publication_date, authors, page,
                document_type, url, content_hash, file_path, chunk_count,
                embedding_count, status, error, created_at, updated_at
            ) VALUES (
                :doc_id, :source, :source_type, :collection, :title, :organization,
                :district, :hazard, :language, :publication_date, :authors, :page,
                :document_type, :url, :content_hash, :file_path, :chunk_count,
                :embedding_count, :status, :error, :created_at, :updated_at
            )
            ON CONFLICT(doc_id) DO UPDATE SET
                source=excluded.source,
                source_type=excluded.source_type,
                collection=excluded.collection,
                title=excluded.title,
                organization=excluded.organization,
                district=excluded.district,
                hazard=excluded.hazard,
                language=excluded.language,
                publication_date=excluded.publication_date,
                authors=excluded.authors,
                page=excluded.page,
                document_type=excluded.document_type,
                url=excluded.url,
                content_hash=excluded.content_hash,
                file_path=excluded.file_path,
                chunk_count=excluded.chunk_count,
                embedding_count=excluded.embedding_count,
                status=excluded.status,
                error=excluded.error,
                updated_at=excluded.updated_at
            """,
            {
                "doc_id": normalized.get("doc_id"),
                "source": normalized.get("source"),
                "source_type": normalized.get("source_type"),
                "collection": normalized.get("collection"),
                "title": normalized.get("title"),
                "organization": normalized.get("organization"),
                "district": normalized.get("district"),
                "hazard": normalized.get("hazard"),
                "language": normalized.get("language"),
                "publication_date": normalized.get("publication_date"),
                "authors": normalized.get("authors"),
                "page": normalized.get("page"),
                "document_type": normalized.get("document_type"),
                "url": normalized.get("url"),
                "content_hash": normalized.get("content_hash"),
                "file_path": normalized.get("file_path"),
                "chunk_count": normalized.get("chunk_count") or 0,
                "embedding_count": normalized.get("embedding_count") or 0,
                "status": normalized.get("status") or "processed",
                "error": normalized.get("error"),
                "created_at": now,
                "updated_at": now,
            },
        )
        self.conn.commit()

    def get_by_doc_id(self, doc_id: str) -> Optional[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM documents WHERE doc_id = ?", (doc_id,))
        row = cursor.fetchone()
        if not row:
            return None
        columns = [column[0] for column in cursor.description]
        return dict(zip(columns, row))

    def get_by_content_hash(self, content_hash: str) -> Optional[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM documents WHERE content_hash = ?", (content_hash,))
        row = cursor.fetchone()
        if not row:
            return None
        columns = [column[0] for column in cursor.description]
        return dict(zip(columns, row))

    def list_documents(self) -> List[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM documents ORDER BY updated_at DESC")
        rows = cursor.fetchall()
        columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, row)) for row in rows]

    def close(self) -> None:
        self.conn.close()

    def statistics(self) -> Dict[str, Any]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM documents")
        total = cursor.fetchone()[0]
        return {"documents_stored": total}
