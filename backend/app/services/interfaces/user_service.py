"""
app/services/interfaces/user_service.py
───────────────────────────────────────
Interface for the User service.
"""

import uuid
from abc import ABC, abstractmethod

from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate


class IUserService(ABC):
    """Abstract interface for User business logic."""

    @abstractmethod
    async def get_all_users(self, skip: int = 0, limit: int = 20) -> tuple[list[User], int]:
        """Fetch paginated users."""
        pass

    @abstractmethod
    async def get_user_by_id(self, user_id: uuid.UUID) -> User:
        """Fetch a single user or raise NotFound."""
        pass

    @abstractmethod
    async def create_user(self, data: UserCreate) -> User:
        """Create a new user."""
        pass

    @abstractmethod
    async def update_user(self, user_id: uuid.UUID, data: UserUpdate) -> User:
        """Update an existing user."""
        pass

    @abstractmethod
    async def delete_user(self, user_id: uuid.UUID) -> None:
        """Soft-delete a user."""
        pass
