import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .config.config import config
from .collectors.dataset_metadata_collector import DatasetMetadataCollector
from .collectors.documentation_website_collector import DocumentationWebsiteCollector
from .collectors.government_collector import GovernmentDocumentsCollector
from .collectors.local_documents_collector import LocalDocumentsCollector
from .collectors.news_collector import NewsCollector
from .collectors.project_repo_collector import ProjectRepositoryCollector
from .collectors.research_papers_collector import ResearchPapersCollector
from .knowledge.store import KnowledgeStore, safe_document_id
from .metadata.storage import MetadataStore
from .statistics.stats import StatisticsWriter
from .processors.deduper import compute_content_hash
from .processors.pipeline import KnowledgePipeline
from .vectorstores.faiss_adapter import FaissAdapter

logger = logging.getLogger(__name__)


class KnowledgeEngine:
    TARGET_COLLECTOR_MAP = {
        "project": ProjectRepositoryCollector,
        "project_repo": ProjectRepositoryCollector,
        "local_documents": LocalDocumentsCollector,
        "government": GovernmentDocumentsCollector,
        "research": ResearchPapersCollector,
        "datasets": DatasetMetadataCollector,
        "news": NewsCollector,
        "documentation": DocumentationWebsiteCollector,
        "manuals": DocumentationWebsiteCollector,
    }

    def __init__(self) -> None:
        self.config = config
        self.metadata_store = MetadataStore(Path(self.config["metadata_db"]))
        self.knowledge_store = KnowledgeStore(Path(self.config["knowledge_root"]))
        self.pipeline = KnowledgePipeline()
        self.vectorstore = FaissAdapter(namespace=self.config.get("vectorstore_namespace", "default"))
        self.stats_writer = StatisticsWriter(Path(self.config["manifest_path"]), Path(self.config["log_dir"]))
        self.embedder = None
        self.result_stats: Dict[str, Any] = {}

    def _load_embedding_model(self):
        if self.embedder is None:
            try:
                from RAG_project.utils.singletons import get_embedding_model
            except ImportError as exc:
                raise RuntimeError("Unable to import RAG_project embedding model.") from exc
            self.embedder = get_embedding_model()
        return self.embedder

    def _collector_for_target(self, target: str):
        collector_cls = self.TARGET_COLLECTOR_MAP.get(target)
        if not collector_cls:
            raise ValueError(f"Unknown ingest target: {target}")
        return collector_cls(self.config)

    def run(self, targets: List[str], force: bool = False, dry_run: bool = False, since: Optional[datetime] = None, limit: Optional[int] = None) -> Dict[str, Any]:
        run_id = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        started_at = datetime.utcnow()
        self.result_stats = {
            "run_id": run_id,
            "targets": targets,
            "force": force,
            "dry_run": dry_run,
            "documents_processed": 0,
            "chunks_created": 0,
            "embeddings_created": 0,
            "duplicates_removed": 0,
            "errors": 0,
            "per_collection": {},
        }

        if not dry_run:
            self.vectorstore.load()

        for target in targets:
            logger.info(f"Starting ingestion target: {target}")
            collector = self._collector_for_target(target)
            sources = collector.discover()
            if limit is not None:
                sources = sources[:limit]
            collection_stats = {
                "documents": 0,
                "chunks": 0,
                "embeddings": 0,
                "duplicates": 0,
                "errors": 0,
            }
            for source in sources:
                try:
                    if self._should_skip_source(source, since) and not force:
                        continue
                    raw_documents = collector.fetch(source)
                    if not raw_documents:
                        continue
                    raw_texts = [str(item.get("page_content", "")) for item in raw_documents]
                    doc_text = "\n\n".join(raw_texts)
                    content_hash = compute_content_hash(doc_text)
                    source.metadata["content_hash"] = content_hash
                    source.metadata["doc_id"] = safe_document_id(f"{source.source_type}:{source.source_id}:{content_hash[:12]}")
                    if self.metadata_store.get_by_content_hash(content_hash) and not force:
                        logger.info(f"Skipping unchanged document: {source.source_id}")
                        continue
                    raw_hashes = {compute_content_hash(text) for text in raw_texts if text}
                    duplicates_removed = max(0, len(raw_texts) - len(raw_hashes))
                    collection_stats["duplicates"] += duplicates_removed
                    self.result_stats["duplicates_removed"] += duplicates_removed
                    chunks = self.pipeline.process(raw_documents)
                    if not chunks:
                        logger.warning(f"No chunks created for source {source.source_id}")
                        collection_stats["errors"] += 1
                        continue
                    collection_stats["documents"] += 1
                    collection_stats["chunks"] += len(chunks)
                    self.result_stats["documents_processed"] += 1
                    self.result_stats["chunks_created"] += len(chunks)

                    embedder = self._load_embedding_model()
                    valid_chunks, embeddings = embedder.embed_documents(chunks)
                    collection_stats["embeddings"] += len(valid_chunks)
                    self.result_stats["embeddings_created"] += len(valid_chunks)

                    if not dry_run:
                        self.vectorstore.upsert(valid_chunks, embeddings)
                        self.knowledge_store.persist_document(
                            metadata={**source.metadata, "chunk_count": len(valid_chunks), "embedding_count": len(valid_chunks), "status": "processed"},
                            raw_text=doc_text,
                            chunks=valid_chunks,
                        )
                        self.metadata_store.upsert_document({
                            **source.metadata,
                            "chunk_count": len(valid_chunks),
                            "embedding_count": len(valid_chunks),
                            "status": "processed",
                        })
                except Exception as exc:
                    logger.exception(f"Failed to process source {source.source_id}: {exc}")
                    collection_stats["errors"] += 1
                    self.result_stats["errors"] += 1
            self.result_stats["per_collection"][target] = collection_stats

        elapsed = (datetime.utcnow() - started_at).total_seconds()
        manifest = {
            "run_id": run_id,
            "run_type": "manual" if since is None else "incremental",
            "started_at": started_at.isoformat() + "Z",
            "finished_at": datetime.utcnow().isoformat() + "Z",
            "elapsed_seconds": elapsed,
            **self.result_stats,
        }
        self.stats_writer.write_manifest(run_id, manifest["run_type"], manifest)
        return manifest

    def _should_skip_source(self, source: Any, since: Optional[datetime]) -> bool:
        if since is None:
            return False
        metadata = source.metadata
        publication_date = metadata.get("publication_date")
        if publication_date:
            try:
                parsed = datetime.fromisoformat(publication_date)
                return parsed < since
            except Exception:
                return False
        return False
