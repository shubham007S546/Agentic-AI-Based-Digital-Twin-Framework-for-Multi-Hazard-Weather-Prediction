"""
app/models/digital_twin.py
──────────────────────────
Digital Twin state and simulation models.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import District, SimulationStatus
from app.database.base import Base, TimestampMixin, UUIDMixin


class TwinState(Base, UUIDMixin, TimestampMixin):
    """
    Represents the synchronized "current state" of the digital twin for a district.
    Updated frequently by the TwinSyncAgent.
    Maintains a historical ledger so we can replay past events.
    """
    
    __tablename__ = "twin_states"

    district: Mapped[District] = mapped_column(
        Enum(District, name="twin_district_enum", native_enum=True),
        index=True,
        nullable=False,
    )
    
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    
    # State components as JSONB for dynamic schema evolution
    weather_state: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    hydrological_state: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    geological_state: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    infrastructure_state: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    
    # Is this the latest state for this district? (optimized for fast querying)
    is_latest: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    def __repr__(self) -> str:
        return f"<TwinState {self.district.name} @ {self.timestamp}>"


class Simulation(Base, UUIDMixin, TimestampMixin):
    """
    A digital twin "What-If" scenario simulation.
    (e.g., "What happens if 200mm of rain falls in Mandi over the next 4 hours?")
    """
    
    __tablename__ = "simulations"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    
    district: Mapped[District] = mapped_column(
        Enum(District, name="simulation_district_enum", native_enum=True),
        index=True,
        nullable=False,
    )
    
    status: Mapped[SimulationStatus] = mapped_column(
        Enum(SimulationStatus, name="simulation_status_enum", native_enum=True),
        default=SimulationStatus.QUEUED,
        index=True,
        nullable=False,
    )
    
    # The baseline state the simulation starts from
    baseline_state_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("twin_states.id"), nullable=False)
    
    # The scenario perturbations (e.g., {"precipitation_multiplier": 2.5})
    scenario_parameters: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    
    # The generated forward-looking state sequence
    simulation_results: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)

    def __repr__(self) -> str:
        return f"<Simulation {self.name} ({self.status.name})>"
