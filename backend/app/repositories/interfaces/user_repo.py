"""
app/repositories/interfaces/user_repo.py
─────────────────────────────────────────
Interface for the User repository.
"""

from abc import ABC, abstractmethod
from typing import Optional
import uuid

from app.models.user import User


class IUserRepository(ABC):
    """Abstract interface for User data access."""

    @abstractmethod
    async def get_by_email(self, email: str) -> Optional[User]:
        """Fetch a user by their email address."""
        pass

    @abstractmethod
    async def get_by_id(self, user_id: uuid.UUID) -> Optional[User]:
        """Fetch a user by their UUID."""
        pass

    @abstractmethod
    async def get_all(self, skip: int = 0, limit: int = 20) -> tuple[list[User], int]:
        """Fetch a paginated list of users, returning (users, total_count)."""
        pass

    @abstractmethod
    async def update(self, user: User) -> User:
        """Update a user record."""
        pass
        
    @abstractmethod
    async def create(self, user: User) -> User:
        """Create a new user record."""
        pass
