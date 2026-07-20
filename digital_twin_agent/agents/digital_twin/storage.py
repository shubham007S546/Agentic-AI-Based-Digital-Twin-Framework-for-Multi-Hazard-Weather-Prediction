"""Persists each scenario run (append-only JSONL, matching the diagram's
"Update Twin State" step and "Database (PostgreSQL)" backend). Swap for
real PostGIS storage once you have it -- same interface either way."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .config import settings
from .logging_config import get_logger

logger = get_logger(__name__)


class TwinStateStore:
    def __init__(self):
        self._redis = None
        if settings.has_redis:
            try:
                import redis
                self._redis = redis.Redis.from_url(settings.redis_url, decode_responses=True)
            except Exception as exc:
                logger.warning("Redis unavailable (%s); scenario state will only be logged to file.", exc)

    def save(self, scenario_result: Dict[str, Any]) -> str:
        scenario_id = f"SCEN-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}-{uuid.uuid4().hex[:6].upper()}"
        record = {"scenario_id": scenario_id, "created_at": datetime.now(timezone.utc).isoformat(), **scenario_result}

        os.makedirs(os.path.dirname(settings.twin_state_log_path) or ".", exist_ok=True)
        with open(settings.twin_state_log_path, "a") as f:
            f.write(json.dumps(record) + "\n")

        if self._redis is not None:
            try:
                self._redis.set(f"scenario:{scenario_id}", json.dumps(record), ex=604800)
                self._redis.lpush("scenarios:recent", scenario_id)
                self._redis.ltrim("scenarios:recent", 0, 199)
            except Exception as exc:
                logger.warning("Redis write failed: %s", exc)

        return scenario_id

    def get(self, scenario_id: str) -> Optional[Dict[str, Any]]:
        if self._redis is not None:
            raw = self._redis.get(f"scenario:{scenario_id}")
            if raw:
                return json.loads(raw)
        if not os.path.exists(settings.twin_state_log_path):
            return None
        with open(settings.twin_state_log_path) as f:
            for line in f:
                record = json.loads(line)
                if record.get("scenario_id") == scenario_id:
                    return record
        return None

    def list_recent(self, limit: int = 20) -> List[Dict[str, Any]]:
        if not os.path.exists(settings.twin_state_log_path):
            return []
        with open(settings.twin_state_log_path) as f:
            lines = f.readlines()
        return [json.loads(line) for line in lines[-limit:]][::-1]


twin_state_store = TwinStateStore()
