"""
app/database/connection.py
───────────────────────────
Async SQLAlchemy engine and connection management.

Design decisions:
  • asyncpg driver is used for maximum async PostgreSQL performance.
    It's ~3x faster than psycopg2 for async workloads (no GIL contention).
  • Connection pool is configured conservatively:
    - pool_size=10: handles normal traffic
    - max_overflow=20: burst capacity (30 total connections max)
    - pool_pre_ping=True: validates connections before use (prevents 'server
      closed connection' errors after idle periods or DB restarts)
    - pool_recycle=1800: recycles connections every 30 minutes to avoid
      stale connections that hit Postgres's default idle timeout.
  • A separate sync engine is created for Alembic migrations. Alembic does
    not support asyncpg natively — it needs psycopg2 (sync).
  • Engine is a module-level singleton initialized once at startup.
    Multiple imports of this module always get the same engine instance.
  • SQLAlchemy's echo=False in production — never log SQL in production
    (security risk: query parameters may contain sensitive data).
"""

from __future__ import annotations

from typing import Optional

import structlog
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings

logger = structlog.get_logger(__name__)

# Module-level singletons — initialized during application lifespan startup
_async_engine: Optional[AsyncEngine] = None
_async_session_factory: Optional[async_sessionmaker[AsyncSession]] = None
_sync_engine: Optional[Engine] = None


async def init_db_engine() -> None:
    """
    Initialize the async SQLAlchemy engine and session factory.
    Called once during application startup (lifespan).
    """
    global _async_engine, _async_session_factory, _sync_engine
    settings = get_settings()

    # ── Async engine (asyncpg) ─────────────────────────────────────────────────
    _async_engine = create_async_engine(
        settings.database.url,
        pool_size=settings.database.pool_size,
        max_overflow=settings.database.max_overflow,
        pool_timeout=settings.database.pool_timeout,
        pool_recycle=settings.database.pool_recycle,
        pool_pre_ping=settings.database.pool_pre_ping,
        echo=settings.database.echo,
        # JSON serialization — use orjson for speed
        json_serializer=_json_serializer,
        json_deserializer=_json_deserializer,
        # asyncpg-specific: statement cache for prepared statement performance
        connect_args={
            "statement_cache_size": 200,
            "command_timeout": 60,
        },
    )

    # ── Session factory ────────────────────────────────────────────────────────
    _async_session_factory = async_sessionmaker(
        bind=_async_engine,
        class_=AsyncSession,
        expire_on_commit=False,  # Don't expire objects after commit (async-safe)
        autocommit=False,
        autoflush=False,
    )

    # ── Sync engine (psycopg2) — for Alembic migrations only ─────────────────
    _sync_engine = create_engine(
        settings.database.sync_url,
        pool_size=2,
        max_overflow=0,
        echo=False,
    )

    logger.info(
        "Database engine initialized",
        pool_size=settings.database.pool_size,
        max_overflow=settings.database.max_overflow,
    )


async def close_db_engine() -> None:
    """Dispose of the async engine — called during application shutdown."""
    global _async_engine, _sync_engine
    if _async_engine:
        await _async_engine.dispose()
        logger.info("Async database engine disposed")
    if _sync_engine:
        _sync_engine.dispose()
        logger.info("Sync database engine disposed")


def get_async_engine() -> AsyncEngine:
    """Return the async engine. Raises if not initialized."""
    if _async_engine is None:
        raise RuntimeError("Database engine not initialized. Call init_db_engine() at startup.")
    return _async_engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the async session factory."""
    if _async_session_factory is None:
        raise RuntimeError("Session factory not initialized.")
    return _async_session_factory


def get_sync_engine() -> Engine:
    """Return the sync engine (Alembic use only)."""
    if _sync_engine is None:
        raise RuntimeError("Sync engine not initialized.")
    return _sync_engine


async def check_db_health() -> bool:
    """
    Verify database connectivity — used by readiness probe.
    Executes a lightweight SELECT 1 query.
    """
    try:
        engine = get_async_engine()
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.warning("Database health check failed", error=str(exc))
        return False


# ── JSON serialization ────────────────────────────────────────────────────────

def _json_serializer(obj: object) -> str:
    """Use orjson for faster JSONB column serialization."""
    import orjson
    return orjson.dumps(obj).decode()


def _json_deserializer(s: str) -> object:
    """Use orjson for faster JSONB column deserialization."""
    import orjson
    return orjson.loads(s)
