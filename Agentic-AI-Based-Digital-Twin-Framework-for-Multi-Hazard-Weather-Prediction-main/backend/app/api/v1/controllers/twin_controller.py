"""
app/api/v1/controllers/twin_controller.py
─────────────────────────────────────────
Digital Twin Controller.
"""

from typing import Annotated
import uuid

from fastapi import Depends

from app.core.enums import District
from app.dependencies.services import get_twin_service
from app.models.digital_twin import Simulation, TwinState
from app.schemas.digital_twin import SimulationCreateRequest
from app.services.interfaces.twin_service import ITwinService


class TwinController:
    """Controller for Digital Twin endpoints."""

    def __init__(
        self,
        twin_service: Annotated[ITwinService, Depends(get_twin_service)],
    ):
        self.twin_service = twin_service

    async def get_current_state(self, district: District) -> TwinState:
        return await self.twin_service.get_current_state(district)

    async def sync_state(self, district: District) -> TwinState:
        return await self.twin_service.synchronize_state(district)

    async def create_simulation(
        self, request: SimulationCreateRequest, created_by: uuid.UUID
    ) -> Simulation:
        return await self.twin_service.create_simulation(request, created_by)

    async def run_simulation(self, simulation_id: uuid.UUID) -> Simulation:
        return await self.twin_service.run_simulation(simulation_id)
