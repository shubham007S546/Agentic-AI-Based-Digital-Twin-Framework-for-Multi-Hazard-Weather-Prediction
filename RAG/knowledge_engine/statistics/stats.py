import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class StatisticsWriter:
    def __init__(self, manifest_path: Path, log_dir: Path) -> None:
        self.manifest_path = manifest_path
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def write_manifest(self, run_id: str, run_type: str, stats: Dict[str, Any]) -> None:
        manifest = {
            "run_id": run_id,
            "run_type": run_type,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "stats": stats,
        }
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        self._append_run_log(manifest)

    def _append_run_log(self, manifest: Dict[str, Any]) -> None:
        run_log = self.log_dir / "ingest_runs.log"
        entry = json.dumps(manifest, ensure_ascii=False)
        with open(run_log, "a", encoding="utf-8") as handle:
            handle.write(entry + "\n")

    def build_summary(self, documents: int, chunks: int, embeddings: int, duplicates_removed: int, errors: int, processing_time_seconds: float, per_collection: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return {
            "documents_processed": documents,
            "chunks_created": chunks,
            "embeddings_created": embeddings,
            "duplicates_removed": duplicates_removed,
            "errors": errors,
            "processing_time_seconds": processing_time_seconds,
            "per_collection": per_collection or {},
        }
