"""
app/schemas/auth.py
────────────────────
Pydantic schemas for authentication requests and responses.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.core.enums import AccessRequestStatus, UserRole


class Token(BaseModel):
    """Token response model."""
    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="Long-lived refresh token")
    token_type: str = Field("bearer", description="Token type")
    expires_in: int = Field(..., description="Access token expiration in seconds")


class LoginRequest(BaseModel):
    """Custom login payload (we prefer JSON over OAuth2 form data for modern APIs)."""
    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., description="User password")

    # Optional fingerprinting for the refresh token device audit
    device_info: str | None = Field(None, description="Client device/browser info")


class RefreshRequest(BaseModel):
    """Refresh token payload."""
    refresh_token: str = Field(..., description="The unexpired refresh token string")
    device_info: str | None = Field(None, description="Client device/browser info")


class TokenData(BaseModel):
    """Data extracted from the JWT token."""
    user_id: str
    role: str
    jti: str


class MeResponse(BaseModel):
    """Current authenticated user's profile — response for GET /me."""
    id: uuid.UUID
    email: EmailStr
    full_name: str
    role: UserRole
    organization: str | None
    department: str | None
    is_active: bool
    is_verified: bool
    last_login: datetime | None

    model_config = ConfigDict(from_attributes=True)


# ── Request Access ──────────────────────────────────────────────────

class RequestAccessCreate(BaseModel):
    """Payload for the 'Request Access' form. Never creates a User directly."""
    full_name: str = Field(..., min_length=1)
    email: EmailStr
    institution: str = Field(..., min_length=1)
    department: str = Field(..., min_length=1)
    purpose: str = Field(..., min_length=1)
    research_area: str | None = None


class AccessRequestResponse(BaseModel):
    """Confirmation returned after submitting a request-access application."""
    id: uuid.UUID
    email: EmailStr
    status: AccessRequestStatus
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ── Password Reset ───────────────────────────────────────────────────

class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., description="The password-reset token from the emailed link")
    new_password: str = Field(..., min_length=8)