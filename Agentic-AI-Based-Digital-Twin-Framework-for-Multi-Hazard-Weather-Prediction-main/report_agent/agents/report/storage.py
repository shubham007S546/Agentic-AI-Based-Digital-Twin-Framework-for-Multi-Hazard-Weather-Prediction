"""Log & Store, matching the diagram's "Log & Store" step. Tracks report
metadata, version, and delivery status (append-only JSONL, matching the
pattern used by Agents 3-5's storage). Version increments per
(report_type, sorted districts) combination, so re-running the same report
tomorrow is tracked as v2, not a fresh unrelated report."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .config import settings
from .logging_config import get_logger

logger = get_logger(__name__)


class ReportStore:
    def __init__(self):
        self._redis = None
        if settings.has_redis:
            try:
                import redis
                self._redis = redis.Redis.from_url(settings.redis_url, decode_responses=True)
            except Exception as exc:
                logger.warning("Redis unavailable (%s); reports will only be logged to file.", exc)

    def _version_key(self, report_type: str, districts: List[str]) -> str:
        return f"{report_type}:{','.join(sorted(districts))}"

    def next_version(self, report_type: str, districts: List[str]) -> int:
        key = self._version_key(report_type, districts)
        if self._redis is not None:
            try:
                return int(self._redis.incr(f"report_version:{key}"))
            except Exception as exc:
                logger.warning("Redis version increment failed: %s", exc)

        existing = [r for r in self._scan_all()
                    if self._version_key(r["metadata"]["report_type"], r["metadata"]["districts"]) == key]
        return len(existing) + 1

    def new_report_id(self) -> str:
        return f"RPT-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}-{uuid.uuid4().hex[:6].upper()}"

    def save(self, record: Dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(settings.report_log_path) or ".", exist_ok=True)
        with open(settings.report_log_path, "a") as f:
            f.write(json.dumps(record) + "\n")

        if self._redis is not None:
            try:
                report_id = record["metadata"]["report_id"]
                self._redis.set(f"report:{report_id}", json.dumps(record), ex=2592000)  # 30 days
                self._redis.lpush("reports:recent", report_id)
                self._redis.ltrim("reports:recent", 0, 199)
            except Exception as exc:
                logger.warning("Redis write failed: %s", exc)

    def get(self, report_id: str) -> Optional[Dict[str, Any]]:
        if self._redis is not None:
            raw = self._redis.get(f"report:{report_id}")
            if raw:
                return json.loads(raw)
        for record in self._scan_all():
            if record.get("metadata", {}).get("report_id") == report_id:
                return record
        return None

    def _scan_all(self) -> List[Dict[str, Any]]:
        if not os.path.exists(settings.report_log_path):
            return []
        with open(settings.report_log_path) as f:
            return [json.loads(line) for line in f]

    def list_recent(self, limit: int = 20) -> List[Dict[str, Any]]:
        return list(reversed(self._scan_all()))[:limit]


report_store = ReportStore()
