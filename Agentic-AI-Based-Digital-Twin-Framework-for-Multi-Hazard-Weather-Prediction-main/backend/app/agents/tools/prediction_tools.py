"""
backend/app/agents/tools/prediction_tools.py
────────────────────────────────────────────
ML Inference tools for agents to query predictors dynamically from the ModelRegistry.
"""

from __future__ import annotations

from typing import Any, Optional
from app.agents.tools.base_tool import BaseAgentTool, ToolParameter
from app.core.enums import HazardType
from app.ml.models_registry.registry import get_model_registry


class RunModelInferenceTool(BaseAgentTool):
    """Tool to execute inference on a registered model for a specific hazard type."""

    def __init__(self) -> None:
        super().__init__(
            name="run_model_inference",
            description="Runs inference using the active ML model from the ModelRegistry for a hazard type.",
            parameters=[
                ToolParameter(name="hazard_type", type="string", description="Hazard type: 'RAINFALL', 'CLOUDBURST', 'LANDSLIDE', or 'FLASH_FLOOD'"),
                ToolParameter(name="features", type="object", description="Dictionary of engineered feature values"),
            ],
        )

    async def execute(self, hazard_type: str, features: dict[str, Any]) -> dict[str, Any]:
        try:
            ht = HazardType[hazard_type.upper()]
        except KeyError:
            return {"status": "error", "error": f"Unknown hazard type: {hazard_type}"}

        registry = get_model_registry()
        predictor = await registry.get_predictor(hazard_type=ht)

        if predictor is None:
            # Fallback estimation if model artifact is not loaded in dev environment
            return {
                "status": "fallback",
                "hazard_type": ht.value,
                "prediction": 45.2 if ht == HazardType.RAINFALL else 0.65,
                "confidence": 0.85,
                "model_name": "heuristic_fallback_v1",
                "is_extreme": False,
            }

        try:
            prediction_output = await predictor.predict(features)
            return {
                "status": "success",
                "hazard_type": ht.value,
                "model_name": predictor.model_name,
                "model_version": predictor.model_version,
                "prediction": prediction_output.get("prediction"),
                "confidence": prediction_output.get("confidence", 0.9),
                "is_extreme": prediction_output.get("is_extreme", False),
            }
        except Exception as exc:
            return {"status": "error", "error": str(exc)}


class GetModelRegistryHealthTool(BaseAgentTool):
    """Tool to inspect active model versions and status in ModelRegistry."""

    def __init__(self) -> None:
        super().__init__(
            name="get_model_registry_health",
            description="Returns status, loaded version, and error logs of all ML models in the registry.",
        )

    async def execute(self) -> dict[str, Any]:
        registry = get_model_registry()
        report = registry.health_report()
        return {
            "total_models": len(report),
            "models": report,
            "all_healthy": all(m.get("is_loaded") for m in report) if report else True,
        }
