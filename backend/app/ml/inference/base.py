"""
app/ml/inference/base.py
────────────────────────
Base interface for all machine learning models in the platform.
"""

from abc import ABC, abstractmethod
from typing import Any


class IModelPredictor(ABC):
    """
    Abstract interface for ML model inference.
    Whether the model is PyTorch, XGBoost, or Scikit-Learn, it must implement this contract.
    """

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Unique identifier for the model (e.g., 'xgboost_rainfall_v1')."""
        pass

    @property
    @abstractmethod
    def model_version(self) -> str:
        """Version tag (e.g., '1.0.0')."""
        pass

    @abstractmethod
    async def load(self) -> None:
        """
        Load model weights into memory. 
        Can be called during application startup to warm up the cache.
        """
        pass

    @abstractmethod
    async def predict(self, features: dict[str, Any]) -> dict[str, Any]:
        """
        Run inference on the provided features.
        Returns a dictionary containing the prediction and confidence scores.
        """
        pass
