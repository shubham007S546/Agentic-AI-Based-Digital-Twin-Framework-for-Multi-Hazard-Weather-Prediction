"""Stores every alert generated (append-only JSONL log, keyed by alert_id),
matching the diagram's "Log & Update" step and "Database (PostgreSQL)"
backend. JSONL keeps this runnable with zero infra; swap `append`/`get`/
`list_recent` for real Postgres queries once you wire that up."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from .config import settings
from .logging_config import get_logger

logger = get_logger(__name__)


class AlertStore:
    def __init__(self):
        self._redis = None
        if settings.has_redis:
            try:
                import redis
                self._redis = redis.Redis.from_url(settings.redis_url, decode_responses=True)
            except Exception as exc:
                logger.warning("Redis unavailable (%s); alerts will only be logged to file.", exc)

    def append(self, alert: Dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(settings.alert_log_path) or ".", exist_ok=True)
        with open(settings.alert_log_path, "a") as f:
            f.write(json.dumps(alert) + "\n")

        if self._redis is not None:
            try:
                self._redis.set(f"alert:{alert['alert_id']}", json.dumps(alert), ex=604800)  # 7 days
                self._redis.lpush("alerts:recent", alert["alert_id"])
                self._redis.ltrim("alerts:recent", 0, 199)
            except Exception as exc:
                logger.warning("Redis write failed: %s", exc)

    def get(self, alert_id: str) -> Optional[Dict[str, Any]]:
        if self._redis is not None:
            raw = self._redis.get(f"alert:{alert_id}")
            if raw:
                return json.loads(raw)
        return self._scan_file(alert_id)

    def _scan_file(self, alert_id: str) -> Optional[Dict[str, Any]]:
        if not os.path.exists(settings.alert_log_path):
            return None
        with open(settings.alert_log_path) as f:
            for line in f:
                record = json.loads(line)
                if record.get("alert_id") == alert_id:
                    return record
        return None

    def list_recent(self, limit: int = 20) -> List[Dict[str, Any]]:
        if self._redis is not None:
            try:
                ids = self._redis.lrange("alerts:recent", 0, limit - 1)
                records = [self.get(i) for i in ids]
                return [r for r in records if r is not None]
            except Exception as exc:
                logger.warning("Redis read failed, falling back to file: %s", exc)

        if not os.path.exists(settings.alert_log_path):
            return []
        with open(settings.alert_log_path) as f:
            lines = f.readlines()
        return [json.loads(line) for line in lines[-limit:]][::-1]


alert_store = AlertStore()
