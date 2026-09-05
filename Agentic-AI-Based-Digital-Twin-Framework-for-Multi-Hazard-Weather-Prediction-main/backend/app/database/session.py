"""
app/database/session.py
────────────────────────
FastAPI dependency for database sessions.

Design decisions:
  • Uses async generator (yield) to provide a single session per request.
  • Commits automatically on success.
  • Rolls back automatically on exception (prevents dirty sessions).
  • Always closes the session (returns connection to pool) in the finally block.
  • Used as a FastAPI Depends() injection in controllers/routers.
"""

from __future__ import annotations

from typing import AsyncGenerator

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError

from app.database.connection import get_session_factory
from app.exceptions.base import DatabaseError

logger = structlog.get_logger(__name__)


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI Dependency that yields an AsyncSession.
    
    Usage in router:
        @router.get("/users")
        async def get_users(db: AsyncSession = Depends(get_async_db)):
            ...
    """
    session_factory = get_session_factory()
    
    async with session_factory() as session:
        try:
            yield session
            if session.is_active:
                await session.commit()
        except SQLAlchemyError as exc:
            try:
                if session.is_active:
                    await session.rollback()
            except Exception:
                pass
            logger.error("Database session rollback due to SQLAlchemy error", error=str(exc))
            raise DatabaseError("A database error occurred during the transaction.") from exc
        except Exception as exc:
            try:
                if session.is_active:
                    await session.rollback()
            except Exception:
                pass
            logger.error("Database session rollback due to unexpected error", error=str(exc))
            raise
        finally:
            await session.close()
