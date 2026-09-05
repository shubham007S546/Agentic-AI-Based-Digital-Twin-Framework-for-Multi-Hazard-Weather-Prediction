"""
app/repositories/twin_repo_impl.py
──────────────────────────────────
SQLAlchemy implementation of the Digital Twin repository.
"""

import uuid
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import District
from app.models.digital_twin import Simulation, TwinState
from app.repositories.interfaces.twin_repo import ITwinRepository


class TwinRepositoryImpl(ITwinRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_latest_state(self, district: District) -> Optional[TwinState]:
        stmt = (
            select(TwinState)
            .where(TwinState.district == district, TwinState.is_latest == True)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_state(self, state: TwinState) -> TwinState:
        # Unflag the previous latest state for this district
        stmt = (
            update(TwinState)
            .where(TwinState.district == state.district, TwinState.is_latest == True)
            .values(is_latest=False)
        )
        await self.session.execute(stmt)
        
        # Ensure the new state is flagged as latest
        state.is_latest = True
        self.session.add(state)
        await self.session.flush()
        return state

    async def get_simulation(self, simulation_id: uuid.UUID) -> Optional[Simulation]:
        stmt = select(Simulation).where(Simulation.id == simulation_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_simulation(self, simulation: Simulation) -> Simulation:
        self.session.add(simulation)
        await self.session.flush()
        return simulation

    async def update_simulation(self, simulation: Simulation) -> Simulation:
        await self.session.flush()
        return simulation
