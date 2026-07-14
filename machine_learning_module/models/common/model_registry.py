"""
ModelRegistry: tracks trained model artifacts (path + metrics + metadata)
across experiments so ModelComparator (or a human) can find the best one.

Backed by a single JSON file so it needs no external services; safe for a
single-machine research/dev workflow.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


class ModelRegistry:
    def __init__(self, registry_path: str = "artifacts/model_registry.json"):
        self.registry_path = Path(registry_path)
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.registry_path.exists():
            self._write({"entries": []})

    def _read(self) -> dict:
        with open(self.registry_path, "r") as f:
            return json.load(f)

    def _write(self, data: dict) -> None:
        with open(self.registry_path, "w") as f:
            json.dump(data, f, indent=2, default=str)

    def register(
        self,
        model_name: str,
        experiment_name: str,
        artifact_path: str,
        task_type: str,
        metrics: dict,
        params: Optional[dict] = None,
    ) -> dict:
        entry = {
            "model_name": model_name,
            "experiment_name": experiment_name,
            "artifact_path": artifact_path,
            "task_type": task_type,
            "metrics": metrics,
            "params": params or {},
            "registered_at": datetime.now(timezone.utc).isoformat(),
        }
        data = self._read()
        data["entries"].append(entry)
        self._write(data)
        return entry

    def list_entries(self, model_name: Optional[str] = None) -> list:
        entries = self._read()["entries"]
        if model_name:
            entries = [e for e in entries if e["model_name"] == model_name]
        return entries

    def best(self, metric: str, higher_is_better: bool = True, model_name: Optional[str] = None) -> Optional[dict]:
        entries = self.list_entries(model_name)
        entries = [e for e in entries if metric in e["metrics"]]
        if not entries:
            return None
        return max(entries, key=lambda e: e["metrics"][metric]) if higher_is_better \
            else min(entries, key=lambda e: e["metrics"][metric])
