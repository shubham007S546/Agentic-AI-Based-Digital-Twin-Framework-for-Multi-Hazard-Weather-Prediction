"""
ModelComparator: builds a side-by-side comparison table across multiple
trained models (e.g. random_forest vs xgboost vs lightgbm) using entries
pulled from a ModelRegistry.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from .model_registry import ModelRegistry


class ModelComparator:
    def __init__(self, registry: ModelRegistry):
        self.registry = registry

    def compare(self, model_names: Optional[list] = None) -> pd.DataFrame:
        entries = self.registry.list_entries()
        if model_names:
            entries = [e for e in entries if e["model_name"] in model_names]

        if not entries:
            return pd.DataFrame()

        rows = []
        for e in entries:
            row = {
                "model_name": e["model_name"],
                "experiment_name": e["experiment_name"],
                "task_type": e["task_type"],
                "registered_at": e["registered_at"],
            }
            row.update(e["metrics"])
            rows.append(row)

        df = pd.DataFrame(rows)
        return df.sort_values("model_name").reset_index(drop=True)

    def rank_by(self, metric: str, higher_is_better: bool = True, model_names: Optional[list] = None) -> pd.DataFrame:
        df = self.compare(model_names)
        if df.empty or metric not in df.columns:
            return df
        return df.sort_values(metric, ascending=not higher_is_better).reset_index(drop=True)
