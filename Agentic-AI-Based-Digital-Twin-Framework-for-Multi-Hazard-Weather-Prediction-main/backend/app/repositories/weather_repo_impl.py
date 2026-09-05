"""
app/repositories/weather_repo_impl.py
─────────────────────────────────────
SQLAlchemy implementation of the Weather repository.
"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import District
from app.models.weather import WeatherObservation
from app.repositories.interfaces.weather_repo import IWeatherRepository


class WeatherRepositoryImpl(IWeatherRepository):
    """SQLAlchemy implementation of IWeatherRepository."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, observation: WeatherObservation) -> WeatherObservation:
        self.session.add(observation)
        await self.session.flush()
        return observation

    async def get_latest_by_district(self, district: District) -> Optional[WeatherObservation]:
        stmt = (
            select(WeatherObservation)
            .where(WeatherObservation.district == district)
            .order_by(WeatherObservation.timestamp.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_recent_by_district(self, district: District, limit: int = 10) -> list[WeatherObservation]:
        stmt = (
            select(WeatherObservation)
            .where(WeatherObservation.district == district)
            .order_by(WeatherObservation.timestamp.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
