"""Post-processing / calibration -- confidence scoring and extreme-event
flagging, matching the diagram's "Post-process & Calibrate" step."""

from __future__ import annotations

from typing import Dict, List, Optional

from .config import settings


def confidence_score(n_history_hours: int, model_loaded: bool, feature_warnings: List[str]) -> float:
    """Simple, transparent confidence heuristic -- not a calibrated
    probability, just a signal of how much to trust this particular
    prediction given data completeness. Replace with real predictive-
    interval / conformal-prediction output once your models support it
    (see the diagram's "Uncertainty" box: Prediction intervals, Quantile
    regression, Monte Carlo Dropout, Confidence score)."""
    if not model_loaded:
        return 0.0
    score = 1.0
    if n_history_hours < 72:
        score -= 0.15 * (72 - n_history_hours) / 72
    score -= 0.05 * len(feature_warnings)
    return round(max(0.0, min(1.0, score)), 2)


def is_extreme_rainfall(predicted_mm: Optional[float]) -> bool:
    if predicted_mm is None:
        return False
    return predicted_mm >= settings.cloudburst_threshold_mm


def is_extreme_probability(probability: Optional[float], threshold: float = 0.7) -> bool:
    if probability is None:
        return False
    return probability >= threshold
