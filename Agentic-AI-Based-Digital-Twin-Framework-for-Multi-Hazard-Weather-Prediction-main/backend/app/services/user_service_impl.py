"""
app/services/user_service_impl.py
─────────────────────────────────
Implementation of IUserService.
"""

import uuid
from datetime import UTC, datetime

from app.exceptions.domain import DuplicateEmailError, UserNotFoundError
from app.models.user import User
from app.repositories.interfaces.user_repo import IUserRepository
from app.schemas.user import UserCreate, UserUpdate
from app.security.authentication.passwords import get_password_hash
from app.services.interfaces.user_service import IUserService


class UserServiceImpl(IUserService):
    def __init__(self, user_repo: IUserRepository):
        self.user_repo = user_repo

    async def get_all_users(self, skip: int = 0, limit: int = 20) -> tuple[list[User], int]:
        return await self.user_repo.get_all(skip=skip, limit=limit)

    async def get_user_by_id(self, user_id: uuid.UUID) -> User:
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise UserNotFoundError(user_id)
        return user

    async def create_user(self, data: UserCreate) -> User:
        existing = await self.user_repo.get_by_email(data.email)
        if existing:
            raise DuplicateEmailError(data.email)

        user = User(
            email=data.email,
            full_name=data.full_name,
            role=data.role,
            hashed_password=get_password_hash(data.password),
            is_active=True,
            is_verified=False,
        )
        return await self.user_repo.create(user)

    async def update_user(self, user_id: uuid.UUID, data: UserUpdate) -> User:
        user = await self.get_user_by_id(user_id)
        
        if data.full_name is not None:
            user.full_name = data.full_name
        if data.role is not None:
            user.role = data.role
        if data.is_active is not None:
            user.is_active = data.is_active

        return await self.user_repo.update(user)

    async def delete_user(self, user_id: uuid.UUID) -> None:
        user = await self.get_user_by_id(user_id)
        # Soft delete
        user.is_deleted = True
        user.deleted_at = datetime.now(UTC)
        user.is_active = False
        await self.user_repo.update(user)
