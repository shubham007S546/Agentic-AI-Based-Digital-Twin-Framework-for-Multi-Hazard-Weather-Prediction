"""
app/agents/explainability_agent.py
────────────────────────────────────
Agent 10 — Explainability Agent

Responsibility:
  • Run post-hoc XAI (Explainable AI) analysis on PredictionRequest records
    using SHAP values, LIME explanations, or feature importance extraction
  • Identify the top driving features for each HIGH/CRITICAL prediction
  • Attach explanation payloads to PredictionRequest.prediction_result JSONB
  • Generate human-readable explanation summaries for disaster officers

Models used:
  • PredictionRequest — reads prediction_result and input_features;
                         writes explanation data back into prediction_result
  • ModelRegistry    — loads the same model that produced the prediction
                         to run SHAP TreeExplainer / LinearExplainer
"""

from __future__ import annotations

from typing import Any

from app.agents.base_agent import BaseAgent
from app.core.enums import AgentName, District, HazardType


# Maximum number of features to include in an explanation
_TOP_K_FEATURES = 5


class ExplainabilityAgent(BaseAgent):
    """
    Post-hoc XAI agent — produces SHAP / feature-importance explanations
    for ML predictions and attaches them to the PredictionRequest audit record.
    """

    def __init__(self) -> None:
        super().__init__(name=AgentName.EXPLAINABILITY, version="1.0.0")

    @property
    def description(self) -> str:
        return (
            "Runs SHAP or LIME explainability analysis on PredictionRequest records, "
            f"extracting the top {_TOP_K_FEATURES} driving features for each prediction "
            "and writing human-readable explanations back into the prediction record."
        )

    def _get_timeout_seconds(self) -> float:
        return 180.0

    async def _run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        XAI pipeline.

        Payload can specify:
          - prediction_ids: list of UUIDs to explain  (default: recent high-risk predictions)
          - method: "shap" | "lime" | "feature_importance"  (default: "shap")
          - top_k: int  (default: _TOP_K_FEATURES)

        Real implementation:
          1. Load PredictionRequest records for given IDs (or query latest HIGH/CRITICAL)
          2. For each record:
             a. Retrieve model via model_registry.get_predictor(hazard_type)
             b. Run SHAP TreeExplainer on model with record.input_features
             c. Sort shap_values by magnitude → top-K features
             d. Build natural-language summary:
                "High landslide risk driven by: soil_moisture (67%), precipitation (23%), ..."
             e. Append explanation dict to record.prediction_result["explanation"]
             f. Save updated record
          3. Return summary of explanations generated
        """
        prediction_ids: list[str] = payload.get("prediction_ids", [])
        method: str = payload.get("method", "shap")
        top_k: int = int(payload.get("top_k", _TOP_K_FEATURES))

        explanations_generated: list[dict] = []

        # When no specific IDs provided, explain recent high-risk predictions
        if not prediction_ids:
            self._logger.info(
                "No prediction IDs provided — will explain latest HIGH/CRITICAL predictions",
                method=method,
            )
            # Real: prediction_ids = await prediction_repo.get_high_risk_ids(limit=10)

        for pred_id in prediction_ids:
            try:
                self._logger.info(
                    "Generating explanation",
                    prediction_id=pred_id,
                    method=method,
                    top_k=top_k,
                )

                # Real:
                # pred = await prediction_repo.get(pred_id)
                # model = await model_registry.get_predictor(pred.hazard_type)
                # shap_values = shap.TreeExplainer(model._model).shap_values(pred.input_features)
                # top_features = sorted(zip(feature_names, shap_values), key=|x| abs(x[1]), reverse=True)[:top_k]
                # explanation = {
                #     "method": method,
                #     "top_features": [{"feature": f, "shap_value": v} for f, v in top_features],
                #     "summary": f"Risk driven by: {', '.join(f for f, _ in top_features[:3])}",
                # }
                # pred.prediction_result["explanation"] = explanation
                # await prediction_repo.update(pred)

                # Stub explanation for now
                stub_explanation = {
                    "prediction_id": pred_id,
                    "method": method,
                    "status": "stub — real SHAP computation pending model loading",
                    "top_features": [],
                }
                explanations_generated.append(stub_explanation)

            except Exception as exc:
                self._logger.error(
                    "Explanation failed",
                    prediction_id=pred_id,
                    error=str(exc),
                )

        return {
            "method": method,
            "top_k": top_k,
            "predictions_requested": len(prediction_ids),
            "explanations_generated": len(explanations_generated),
            "explanations": explanations_generated,
        }
