"""
Per-session conversation memory. Matches the diagram's "Cache Service
(Redis)" backend service: uses Redis if REDIS_URL is configured, otherwise
falls back to a plain in-process dict (fine for local dev / single-process
deployments, but won't persist across restarts or scale across multiple
orchestrator instances -- set REDIS_URL for anything beyond that).
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from .config import settings
from .logging_config import get_logger

logger = get_logger(__name__)


class _InMemoryStore:
    def __init__(self):
        self._store: Dict[str, List[Dict[str, str]]] = {}

    def get(self, session_id: str) -> List[Dict[str, str]]:
        return self._store.get(session_id, [])

    def append(self, session_id: str, turn: Dict[str, str], max_turns: int) -> None:
        history = self._store.setdefault(session_id, [])
        history.append(turn)
        if len(history) > max_turns:
            del history[:-max_turns]


class _RedisStore:
    def __init__(self, url: str):
        import redis
        self._client = redis.Redis.from_url(url, decode_responses=True)
        self._fallback = _InMemoryStore()

    def _key(self, session_id: str) -> str:
        return f"orchestrator:session:{session_id}:history"

    def get(self, session_id: str) -> List[Dict[str, str]]:
        try:
            raw = self._client.lrange(self._key(session_id), 0, -1)
            return [json.loads(item) for item in raw]
        except Exception as exc:
            logger.debug("Redis get failed (%s), using local fallback", exc)
            return self._fallback.get(session_id)

    def append(self, session_id: str, turn: Dict[str, str], max_turns: int) -> None:
        try:
            key = self._key(session_id)
            self._client.rpush(key, json.dumps(turn))
            self._client.ltrim(key, -max_turns, -1)
        except Exception as exc:
            logger.debug("Redis append failed (%s), using local fallback", exc)
            self._fallback.append(session_id, turn, max_turns)


class ConversationMemory:
    def __init__(self):
        if settings.has_redis:
            try:
                self._store = _RedisStore(settings.redis_url)
                logger.info("ConversationMemory using Redis at %s", settings.redis_url)
            except Exception as exc:  # connection/import failure -- degrade gracefully
                logger.warning("Redis unavailable (%s); falling back to in-process memory.", exc)
                self._store = _InMemoryStore()
        else:
            self._store = _InMemoryStore()
            logger.info("ConversationMemory using in-process store (set REDIS_URL for persistence).")

    def get_history(self, session_id: str) -> List[Dict[str, str]]:
        return self._store.get(session_id)

    def add_turn(self, session_id: str, user_query: str, response: str) -> None:
        self._store.append(
            session_id,
            {"user": user_query, "assistant": response},
            settings.max_history_turns,
        )


conversation_memory = ConversationMemory()
