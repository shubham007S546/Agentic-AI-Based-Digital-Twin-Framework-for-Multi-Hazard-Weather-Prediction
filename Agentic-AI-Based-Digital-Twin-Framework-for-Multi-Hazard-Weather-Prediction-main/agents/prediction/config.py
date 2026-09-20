"""
Environment-driven configuration for the Prediction Agent.

Required (for real inference)
------------------------------
ML_MODULE_PATH        Path to your machine_learning_module/ folder, so this
                       agent can import your real BasePredictor/model classes
                       and load a trained .joblib artifact. Defaults to
                       "../../machine_learning_module" (adjust to your layout).

RAINFALL_MODEL_PATH    Path to a trained rainfall regression artifact, e.g.
                       "machine_learning_module/artifacts/lightgbm/step2_log1p_lgbm/model.joblib"
RAINFALL_MODEL_ALGO    Which model.py to load it with: "lightgbm" | "xgboost" |
                       "random_forest" | "ensemble" | "deep_learning" | "transformer".
RAINFALL_TARGET_TRANSFORM   "none" | "log1p" -- must match what the artifact was trained with.
SCALER_PARAMS_PATH     Path to ml_ready/scaler_params.csv (mean/std per scaled feature).

Optional
--------
CLOUDBURST_MODEL_PATH / CLOUDBURST_MODEL_ALGO   Same idea, for the cloudburst_flag
                       classifier, once you've trained one. Left unset = stubbed.
LANDSLIDE_MODEL_PATH / LANDSLIDE_MODEL_ALGO     Same, for landslide_risk. Left unset = stubbed.

CLOUDBURST_THRESHOLD_MM   Defaults to 100.0, matching final_preprocessing.py's CLOUDBURST_MM.
PREDICTION_LOG_PATH       Where predictions get appended (JSONL). Defaults to "logs/predictions.jsonl".
REDIS_URL                 Optional -- if set, predictions are also cached/keyed in Redis for fast re-fetch.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _load_dotenv_if_present() -> None:
    try:
        from pathlib import Path
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parent / ".env")
    except ImportError:
        pass


_load_dotenv_if_present()


def _find_default_rainfall_model() -> str:
    env_path = os.getenv("RAINFALL_MODEL_PATH", "")
    if env_path and os.path.exists(env_path):
        return env_path
    from pathlib import Path
    for candidate in [
        Path(__file__).resolve().parents[2] / "backend" / "ml_models" / "rainfall_xgboost.pkl",
        Path(__file__).resolve().parents[2] / "backend" / "ml_models" / "rainfall_lightgbm.pkl",
    ]:
        if candidate.exists():
            return str(candidate)
    return ""


def _find_default_landslide_model() -> str:
    env_path = os.getenv("LANDSLIDE_MODEL_PATH", "")
    if env_path and os.path.exists(env_path):
        return env_path
    from pathlib import Path
    for candidate in [
        Path(__file__).resolve().parents[2] / "backend" / "ml_models" / "xgboost_landslide_risk.pkl",
        Path(__file__).resolve().parents[2] / "ml_ready" / "models" / "xgboost_landslide_risk.pkl",
    ]:
        if candidate.exists():
            return str(candidate)
    return ""


def _find_default_scaler_params() -> str:
    env_path = os.getenv("SCALER_PARAMS_PATH", "")
    if env_path and os.path.exists(env_path):
        return env_path
    from pathlib import Path
    candidate = Path(__file__).resolve().parents[2] / "ml_ready" / "scaler_params.csv"
    if candidate.exists():
        return str(candidate)
    return ""


@dataclass
class Settings:
    ml_module_path: str = os.getenv("ML_MODULE_PATH", "../../machine_learning_module")

    rainfall_model_path: str = _find_default_rainfall_model()
    rainfall_model_algo: str = os.getenv("RAINFALL_MODEL_ALGO", "xgboost")
    rainfall_target_transform: str = os.getenv("RAINFALL_TARGET_TRANSFORM", "none")

    cloudburst_model_path: str = os.getenv("CLOUDBURST_MODEL_PATH", "")
    cloudburst_model_algo: str = os.getenv("CLOUDBURST_MODEL_ALGO", "xgboost")

    landslide_model_path: str = _find_default_landslide_model()
    landslide_model_algo: str = os.getenv("LANDSLIDE_MODEL_ALGO", "xgboost")

    scaler_params_path: str = _find_default_scaler_params()

    cloudburst_threshold_mm: float = float(os.getenv("CLOUDBURST_THRESHOLD_MM", "100.0"))

    prediction_log_path: str = os.getenv("PREDICTION_LOG_PATH", "logs/predictions.jsonl")
    redis_url: str = os.getenv("REDIS_URL", "")

    log_dir: str = os.getenv("PREDICTION_AGENT_LOG_DIR", "logs")

    @property
    def has_rainfall_model(self) -> bool:
        return bool(self.rainfall_model_path)

    @property
    def has_cloudburst_model(self) -> bool:
        return bool(self.cloudburst_model_path)

    @property
    def has_landslide_model(self) -> bool:
        return bool(self.landslide_model_path)

    @property
    def has_scaler(self) -> bool:
        return bool(self.scaler_params_path)

    @property
    def has_redis(self) -> bool:
        return bool(self.redis_url)


settings = Settings()
