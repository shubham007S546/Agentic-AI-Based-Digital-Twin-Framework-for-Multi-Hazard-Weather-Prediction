"""
app/api/v1/controllers/user_controller.py
─────────────────────────────────────────
User Controller class.
"""

import uuid
from typing import Annotated

from fastapi import Depends

from app.dependencies.services import get_user_service
from app.schemas.user import UserCreate, UserUpdate
from app.services.interfaces.user_service import IUserService


class UserController:
    """Controller for user management endpoints."""

    def __init__(
        self,
        user_service: Annotated[IUserService, Depends(get_user_service)],
    ):
        self.user_service = user_service

    async def get_all_users(self, skip: int, limit: int):
        users, total = await self.user_service.get_all_users(skip=skip, limit=limit)
        return users, total

    async def get_user_by_id(self, user_id: uuid.UUID):
        return await self.user_service.get_user_by_id(user_id)

    async def create_user(self, data: UserCreate):
        return await self.user_service.create_user(data)

    async def update_user(self, user_id: uuid.UUID, data: UserUpdate):
        return await self.user_service.update_user(user_id, data)

    async def delete_user(self, user_id: uuid.UUID):
        await self.user_service.delete_user(user_id)
