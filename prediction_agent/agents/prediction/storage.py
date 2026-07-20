"""Stores every prediction made (append-only JSONL log), matching the
diagram's "Save & Log" step and "Database (PostgreSQL)" backend service --
using a plain JSONL file so this runs with zero infra out of the box.
Swap `append` for a real INSERT once you wire up Postgres."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .config import settings
from .logging_config import get_logger

logger = get_logger(__name__)


class PredictionStore:
    def __init__(self):
        self._redis = None
        if settings.has_redis:
            try:
                import redis
                self._redis = redis.Redis.from_url(settings.redis_url, decode_responses=True)
            except Exception as exc:
                logger.warning("Redis unavailable (%s); predictions will only be logged to file.", exc)

    def append(self, result: Dict[str, Any]) -> str:
        prediction_id = str(uuid.uuid4())
        record = {"prediction_id": prediction_id, "stored_at": datetime.now(timezone.utc).isoformat(), **result}

        os.makedirs(os.path.dirname(settings.prediction_log_path) or ".", exist_ok=True)
        with open(settings.prediction_log_path, "a") as f:
            f.write(json.dumps(record) + "\n")

        if self._redis is not None:
            try:
                self._redis.set(f"prediction:{prediction_id}", json.dumps(record), ex=86400)
            except Exception as exc:
                logger.warning("Redis write failed: %s", exc)

        return prediction_id

    def get(self, prediction_id: str) -> Optional[Dict[str, Any]]:
        if self._redis is not None:
            raw = self._redis.get(f"prediction:{prediction_id}")
            if raw:
                return json.loads(raw)
        # fall back to scanning the log file (fine for local dev; use a real
        # DB for anything beyond that)
        if not os.path.exists(settings.prediction_log_path):
            return None
        with open(settings.prediction_log_path) as f:
            for line in f:
                record = json.loads(line)
                if record.get("prediction_id") == prediction_id:
                    return record
        return None


prediction_store = PredictionStore()
