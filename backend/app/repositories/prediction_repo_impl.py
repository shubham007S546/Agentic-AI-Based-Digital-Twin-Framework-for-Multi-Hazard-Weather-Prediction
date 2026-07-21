"""
app/repositories/prediction_repo_impl.py
────────────────────────────────────────
SQLAlchemy implementation of the Prediction repository.
"""

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import District, HazardType
from app.models.prediction import PredictionRequest
from app.repositories.interfaces.prediction_repo import IPredictionRepository


class PredictionRepositoryImpl(IPredictionRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, request: PredictionRequest) -> PredictionRequest:
        self.session.add(request)
        await self.session.flush()
        return request

    async def get_by_id(self, request_id: uuid.UUID) -> Optional[PredictionRequest]:
        stmt = select(PredictionRequest).where(PredictionRequest.id == request_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_recent_by_district_and_hazard(
        self, district: District, hazard: HazardType, limit: int = 10
    ) -> list[PredictionRequest]:
        stmt = (
            select(PredictionRequest)
            .where(
                PredictionRequest.district == district,
                PredictionRequest.hazard_type == hazard
            )
            .order_by(PredictionRequest.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
