"""
app/api/v1/routers/twin_router.py
─────────────────────────────────
Digital Twin API endpoints.
"""

from typing import Annotated
import uuid

from fastapi import APIRouter, Depends, Path, status

from app.api.v1.controllers.twin_controller import TwinController
from app.core.enums import District
from app.dependencies.auth import CurrentUserToken, require_admin
from app.schemas.common import ApiResponse
from app.schemas.digital_twin import (
    SimulationCreateRequest,
    SimulationResponse,
    TwinStateResponse,
)

router = APIRouter()


@router.get(
    "/states/{district}",
    response_model=ApiResponse[TwinStateResponse],
    summary="Get current Digital Twin state",
)
async def get_state(
    district: Annotated[District, Path(...)],
    token_data: CurrentUserToken,
    controller: Annotated[TwinController, Depends()],
) -> ApiResponse[TwinStateResponse]:
    """Fetch the latest synced TwinState for the specified district."""
    state = await controller.get_current_state(district)
    return ApiResponse(data=state)


@router.post(
    "/states/{district}/sync",
    response_model=ApiResponse[TwinStateResponse],
    summary="Force synchronize Twin state",
    dependencies=[Depends(require_admin)],
)
async def sync_state(
    district: Annotated[District, Path(...)],
    controller: Annotated[TwinController, Depends()],
) -> ApiResponse[TwinStateResponse]:
    """Force a live sync of the TwinState from all underlying data sources (Admin only)."""
    state = await controller.sync_state(district)
    return ApiResponse(
        data=state,
        message="Twin state synchronized successfully",
    )


@router.post(
    "/simulations",
    response_model=ApiResponse[SimulationResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create a new Simulation scenario",
)
async def create_simulation(
    payload: SimulationCreateRequest,
    token_data: CurrentUserToken,
    controller: Annotated[TwinController, Depends()],
) -> ApiResponse[SimulationResponse]:
    """Create a new what-if simulation scenario."""
    simulation = await controller.create_simulation(payload, created_by=uuid.UUID(token_data.user_id))
    return ApiResponse(
        data=simulation,
        message="Simulation scenario created",
    )


@router.post(
    "/simulations/{simulation_id}/run",
    response_model=ApiResponse[SimulationResponse],
    summary="Execute a Simulation",
)
async def run_simulation(
    simulation_id: Annotated[uuid.UUID, Path(...)],
    token_data: CurrentUserToken,
    controller: Annotated[TwinController, Depends()],
) -> ApiResponse[SimulationResponse]:
    """Execute a pending simulation scenario."""
    simulation = await controller.run_simulation(simulation_id)
    return ApiResponse(
        data=simulation,
        message=f"Simulation {simulation.status.name}",
    )
