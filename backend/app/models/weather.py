"""
app/models/weather.py
─────────────────────
Weather and environmental observation models.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, Float, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import District, WeatherQuality, WeatherSource
from app.database.base import Base, TimestampMixin, UUIDMixin


class WeatherObservation(Base, UUIDMixin, TimestampMixin):
    """
    Unified weather observation record.
    Aggregates data from multiple sources (IMD, Open-Meteo, GPM) into a common format.
    """
    
    __tablename__ = "weather_observations"
    __table_args__ = (
        UniqueConstraint("district", "source", "timestamp", name="uq_weather_observation"),
    )

    district: Mapped[District] = mapped_column(
        Enum(District, name="district_enum", native_enum=True),
        index=True,
        nullable=False,
    )
    
    source: Mapped[WeatherSource] = mapped_column(
        Enum(WeatherSource, name="weather_source_enum", native_enum=True),
        index=True,
        nullable=False,
    )
    
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    
    # Core variables (normalized)
    temperature_2m: Mapped[float | None] = mapped_column(Float, nullable=True)     # Celsius
    relative_humidity_2m: Mapped[float | None] = mapped_column(Float, nullable=True) # Percent
    surface_pressure: Mapped[float | None] = mapped_column(Float, nullable=True)     # hPa
    wind_speed_10m: Mapped[float | None] = mapped_column(Float, nullable=True)       # km/h
    wind_direction_10m: Mapped[float | None] = mapped_column(Float, nullable=True)   # Degrees
    precipitation: Mapped[float | None] = mapped_column(Float, nullable=True)        # mm
    cloud_cover: Mapped[float | None] = mapped_column(Float, nullable=True)          # Percent
    
    # Soil / Land
    soil_moisture: Mapped[float | None] = mapped_column(Float, nullable=True)        # m3/m3
    
    # Quality control
    quality_flag: Mapped[WeatherQuality] = mapped_column(
        Enum(WeatherQuality, name="weather_quality_enum", native_enum=True),
        default=WeatherQuality.GOOD,
        nullable=False,
    )
    
    # Raw payload from source (for auditing / reprocessing)
    raw_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    def __repr__(self) -> str:
        return f"<WeatherObservation {self.district.name} @ {self.timestamp}>"
