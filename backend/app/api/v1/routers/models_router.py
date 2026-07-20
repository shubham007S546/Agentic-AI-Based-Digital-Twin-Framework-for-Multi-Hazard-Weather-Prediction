"""
app/api/v1/routers/models_router.py
───────────────────────────────────
Model Registry and Serving API endpoints.
"""

from typing import Annotated
from fastapi import APIRouter, Depends, status, Query

from app.core.enums import HazardType
from app.dependencies.auth import CurrentUserToken, require_admin
from app.schemas.common import ApiResponse
from app.ml.models_registry.registry import get_model_registry

router = APIRouter()


@router.get(
    "",
    summary="List all registered models and their versions",
)
async def list_models(
    token_data: CurrentUserToken,
) -> ApiResponse[list[dict]]:
    """
    Retrieve all models in the registry with their version, hazard type, load status, and errors.
    """
    registry = get_model_registry()
    report = registry.health_report()
    return ApiResponse(data=report)


@router.post(
    "/promote",
    summary="Promote a model version to active (or rollback)",
    dependencies=[Depends(require_admin)],
)
async def promote_model(
    hazard_type: HazardType,
    model_name: str,
    version: str,
) -> ApiResponse[dict]:
    """
    Promote a specific model version to be the active serving model for a hazard type.
    This effectively supports model promotion and instant rollbacks.
    """
    registry = get_model_registry()
    success = await registry.set_active_version(hazard_type, model_name, version)
    if success:
        return ApiResponse(
            data={"hazard_type": hazard_type, "model_name": model_name, "version": version},
            message=f"Model version promoted successfully as active for {hazard_type.name}"
        )
    return ApiResponse(
        success=False,
        message="Model promotion failed. Ensure the model is registered.",
    )


@router.post(
    "/ab-test/configure",
    summary="Configure A/B testing routing split",
    dependencies=[Depends(require_admin)],
)
async def configure_ab_split(
    hazard_type: HazardType,
    baseline_version: str,
    challenger_version: str,
    traffic_split: float = Query(0.1, ge=0.0, le=1.0, description="Fraction of traffic routed to challenger"),
) -> ApiResponse[dict]:
    """
    Configure traffic routing split between two model versions for A/B testing.
    """
    registry = get_model_registry()
    registry.set_ab_config(hazard_type, baseline_version, challenger_version, traffic_split)
    return ApiResponse(
        data={
            "hazard_type": hazard_type,
            "baseline": baseline_version,
            "challenger": challenger_version,
            "traffic_split": traffic_split
        },
        message="A/B testing split configured successfully"
    )
