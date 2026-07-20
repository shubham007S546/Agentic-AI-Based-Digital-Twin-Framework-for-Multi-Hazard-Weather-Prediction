"""
app/schemas/notification.py
───────────────────────────
Pydantic schemas for Notifications.
"""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class NotificationDispatchRequest(BaseModel):
    message: str = Field(..., max_length=1000)
    channels: list[str] = Field(default=["email"], description="e.g., email, sms, push")
    recipients: list[str] = Field(..., description="List of emails or phone numbers")
    context: dict[str, Any] = Field(default_factory=dict, description="Template variables")


class NotificationDispatchResponse(BaseModel):
    status: str
    message: str
    dispatched_count: int
    channels_used: list[str]
