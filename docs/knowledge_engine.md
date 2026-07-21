# Knowledge Engine

This new knowledge engine adds an enterprise-grade ingestion and knowledge management layer to the existing RAG project without replacing the working retrieval, embedding, or FAISS pipeline.

## Architecture

- `knowledge_engine/collectors/`: Modular collectors implementing `discover()` and `fetch()`.
- `knowledge_engine/processors/`: Pre-chunk normalization, metadata extraction, hazard identification, deduplication, and chunking wrappers.
- `knowledge_engine/vectorstores/`: Generic vector store adapter layer with a FAISS adapter that wraps the existing FAISS implementation.
- `knowledge_engine/metadata/`: SQLite-backed metadata store for document-level metadata and processing state.
- `knowledge_engine/scheduler/`: Simple scheduler support for manual, daily, weekly, and incremental ingestion.
- `knowledge_engine/statistics/`: Manifest and run log generation.

## CLI

Use the new root CLI: `python ingest.py`

Supported commands:

- `python ingest.py --repo`
- `python ingest.py --government`
- `python ingest.py --research`
- `python ingest.py --datasets`
- `python ingest.py --news`
- `python ingest.py --all`

Common options:

- `--force`: reprocess unchanged sources
- `--dry-run`: perform ingestion validation without persisting vectorstore updates
- `--since YYYY-MM-DD`: ingest only documents published after the provided date
- `--limit N`: limit the number of ingested sources per target
- `--schedule [manual|daily|weekly|incremental]`

## Adding a Collector

1. Add a new collector class in `knowledge_engine/collectors/` that inherits `CollectorBase`.
2. Implement the `discover()` method to return `CollectedSource` entries.
3. Implement the `fetch(source)` method to return raw document objects with `page_content` and `metadata`.
4. Register the collector in `knowledge_engine/orchestrator.py`.

## Knowledge Layout

Ingested knowledge is stored under `knowledge_engine/knowledge/` with collection directories:

- `project/`
- `government/`
- `research/`
- `datasets/`
- `reports/`
- `manuals/`
- `news/`
- `processed/`

The manifest is written to `knowledge_engine/statistics/knowledge_manifest.json` and run events append to `knowledge_engine/logs/ingest_runs.log`.

Ingested documents are also persisted under `knowledge_engine/knowledge/` by collection, with a `document.txt`, `metadata.json`, and `chunks.json` for each ingested source.
