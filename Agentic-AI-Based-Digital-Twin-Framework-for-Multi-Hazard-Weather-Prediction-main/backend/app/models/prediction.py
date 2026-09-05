"""
app/models/prediction.py
─────────────────────────
ML Prediction domain models.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Float, ForeignKey, String, Enum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import District, HazardType, PredictionStatus, PredictionType
from app.database.base import Base, TimestampMixin, UUIDMixin


class PredictionRequest(Base, UUIDMixin, TimestampMixin):
    """
    Log of every prediction request (online or batch) made to the system.
    Used for audit, model monitoring (drift detection), and research.
    """
    
    __tablename__ = "prediction_requests"

    # The user or agent who triggered the prediction
    triggered_by: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    
    # Model tracking
    model_name: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    model_version: Mapped[str] = mapped_column(String(50), nullable=False)
    
    # Context
    district: Mapped[District] = mapped_column(
        Enum(District, name="district_enum", native_enum=True),
        index=True,
        nullable=False,
    )
    hazard_type: Mapped[HazardType] = mapped_column(
        Enum(HazardType, name="hazard_type_enum", native_enum=True),
        index=True,
        nullable=False,
    )
    prediction_type: Mapped[PredictionType] = mapped_column(
        Enum(PredictionType, name="prediction_type_enum", native_enum=True),
        nullable=False,
    )
    
    # Data payloads (JSONB for flexibility as features change)
    input_features: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    prediction_result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    
    # Core output metrics
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    inference_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    
    status: Mapped[PredictionStatus] = mapped_column(
        Enum(PredictionStatus, name="prediction_status_enum", native_enum=True),
        default=PredictionStatus.PENDING,
        index=True,
        nullable=False,
    )
    
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)

    def __repr__(self) -> str:
        return f"<PredictionRequest {self.model_name} ({self.status})>"
