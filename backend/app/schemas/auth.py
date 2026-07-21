"""
app/schemas/auth.py
───────────────────
Pydantic schemas for authentication requests and responses.
"""

from pydantic import BaseModel, ConfigDict, EmailStr, Field


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
