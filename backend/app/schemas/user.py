"""
app/schemas/user.py
───────────────────
Pydantic schemas for User Management.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.core.enums import UserRole


# ── Responses ─────────────────────────────────────────────────────────────────

class UserResponse(BaseModel):
    """User profile data returned to clients."""
    
    id: uuid.UUID
    email: EmailStr
    full_name: str
    role: UserRole
    is_active: bool
    is_verified: bool
    last_login: datetime | None
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


# ── Requests ──────────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    """Payload for creating a new user (admin action)."""
    
    email: EmailStr
    full_name: str
    password: str = Field(..., min_length=8, description="Initial password")
    role: UserRole = Field(default=UserRole.PUBLIC)


class UserUpdate(BaseModel):
    """Payload for updating an existing user."""
    
    full_name: str | None = None
    role: UserRole | None = None
    is_active: bool | None = None


class UserPasswordChange(BaseModel):
    """Payload for changing one's own password."""
    
    current_password: str
    new_password: str = Field(..., min_length=8)
