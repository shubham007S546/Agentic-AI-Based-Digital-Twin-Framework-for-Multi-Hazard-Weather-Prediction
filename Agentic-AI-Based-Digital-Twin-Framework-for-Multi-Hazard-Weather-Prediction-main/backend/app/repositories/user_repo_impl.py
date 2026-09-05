"""
app/repositories/user_repo_impl.py
───────────────────────────────────
SQLAlchemy implementation of the User repository.
"""

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories.interfaces.user_repo import IUserRepository


class UserRepositoryImpl(IUserRepository):
    """SQLAlchemy implementation of IUserRepository."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_email(self, email: str) -> Optional[User]:
        stmt = select(User).where(User.email == email, User.is_deleted == False)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: uuid.UUID) -> Optional[User]:
        stmt = select(User).where(User.id == user_id, User.is_deleted == False)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all(self, skip: int = 0, limit: int = 20) -> tuple[list[User], int]:
        from sqlalchemy import func
        
        # Base query excluding deleted users
        base_query = select(User).where(User.is_deleted == False)
        
        # Count total
        count_stmt = select(func.count()).select_from(base_query.subquery())
        total_count = (await self.session.execute(count_stmt)).scalar_one() or 0
        
        # Fetch page
        stmt = base_query.order_by(User.created_at.desc()).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        users = list(result.scalars().all())
        
        return users, total_count

    async def update(self, user: User) -> User:
        # Changes are already tracked by the session, but we flush to sync DB
        await self.session.flush()
        return user

    async def create(self, user: User) -> User:
        self.session.add(user)
        await self.session.flush()
        return user
