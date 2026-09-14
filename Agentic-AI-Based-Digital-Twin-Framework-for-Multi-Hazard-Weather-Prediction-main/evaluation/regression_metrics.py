"""
evaluation/regression_metrics.py
─────────────────────────────────────────────────────────────────────────────
Regression evaluation utilities for rainfall / hazard prediction models.

Metrics
-------
Standard:
  - RMSE  (Root Mean Squared Error)
  - MAE   (Mean Absolute Error)
  - R²    (Coefficient of Determination)
  - MAPE  (Mean Absolute Percentage Error, guard against zero targets)
  - Bias  (mean signed error = mean(pred − true))

Hydrology-specific:
  - NSE   (Nash-Sutcliffe Efficiency — gold standard in hydrology)
  - KGE   (Kling-Gupta Efficiency — penalises bias, variability, correlation)
  - PBIAS (Percent Bias — signed, favoured by SWAT community)

IMD threshold hit-rates (for each district-alert tier):
  - CSI   (Critical Success Index = TP / (TP + FP + FN)) at 4 thresholds
  - FAR   (False Alarm Ratio)
  - POD   (Probability Of Detection)

Usage
-----
    from evaluation.regression_metrics import RegressionEvaluator
    ev = RegressionEvaluator(y_true, y_pred)
    print(ev.summary())
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional, Sequence

import numpy as np
import pandas as pd

# ── IMD 24-hour rainfall thresholds (mm) ────────────────────────────────────
IMD_THRESHOLDS = {
    "heavy":          64.5,   # Yellow Watch
    "very_heavy":    115.6,   # Orange Warning
    "extremely_heavy": 204.5, # Red Alert
    "cloudburst_proxy": 50.0, # proxy for 1-hour burst in 24h dataset
}


# ── Result dataclasses ───────────────────────────────────────────────────────

@dataclass
class ThresholdScores:
    threshold_mm: float
    label: str
    pod: float   # Probability of Detection
    far: float   # False Alarm Ratio
    csi: float   # Critical Success Index
    n_events: int


@dataclass
class RegressionResult:
    rmse: float
    mae: float
    r2: float
    mape: float
    bias: float
    nse: float
    kge: float
    pbias: float
    n_samples: int
    threshold_scores: list[dict]  # serialisable form of ThresholdScores

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def to_dataframe_row(self, model_name: str = "") -> pd.Series:
        d = self.to_dict()
        d.pop("threshold_scores")
        d["model_name"] = model_name
        return pd.Series(d)


# ── Core evaluator ───────────────────────────────────────────────────────────

class RegressionEvaluator:
    """
    Compute a rich suite of regression metrics for rainfall / hazard prediction.

    Parameters
    ----------
    y_true : array-like, shape (n,)
    y_pred : array-like, shape (n,)
    thresholds : dict[str, float], optional
        Override the default IMD thresholds used for threshold-based scores.
    """

    def __init__(
        self,
        y_true: "np.ndarray | pd.Series | Sequence",
        y_pred:  "np.ndarray | pd.Series | Sequence",
        thresholds: Optional[dict] = None,
    ) -> None:
        self.y_true = np.asarray(y_true, dtype=float).ravel()
        self.y_pred = np.asarray(y_pred, dtype=float).ravel()
        if len(self.y_true) != len(self.y_pred):
            raise ValueError(
                f"y_true length {len(self.y_true)} != y_pred length {len(self.y_pred)}"
            )
        self.thresholds = thresholds or IMD_THRESHOLDS

    # ── Standard metrics ─────────────────────────────────────────────────────

    def rmse(self) -> float:
        return float(np.sqrt(np.mean((self.y_pred - self.y_true) ** 2)))

    def mae(self) -> float:
        return float(np.mean(np.abs(self.y_pred - self.y_true)))

    def r2(self) -> float:
        ss_res = np.sum((self.y_true - self.y_pred) ** 2)
        ss_tot = np.sum((self.y_true - self.y_true.mean()) ** 2)
        if ss_tot == 0:
            return float("nan")
        return float(1.0 - ss_res / ss_tot)

    def mape(self) -> float:
        """MAPE ignoring zero-target samples (avoids division by zero)."""
        mask = self.y_true != 0
        if mask.sum() == 0:
            return float("nan")
        return float(np.mean(np.abs((self.y_true[mask] - self.y_pred[mask]) / self.y_true[mask])) * 100)

    def bias(self) -> float:
        """Mean signed error: positive = over-prediction."""
        return float(np.mean(self.y_pred - self.y_true))

    # ── Hydrology-specific ───────────────────────────────────────────────────

    def nse(self) -> float:
        """
        Nash-Sutcliffe Efficiency.
        NSE = 1  →  perfect. NSE = 0  →  no better than the mean.
        NSE < 0  →  climatological mean is a better predictor.
        """
        obs_mean = self.y_true.mean()
        numerator = np.sum((self.y_pred - self.y_true) ** 2)
        denominator = np.sum((self.y_true - obs_mean) ** 2)
        if denominator == 0:
            return float("nan")
        return float(1.0 - numerator / denominator)

    def kge(self) -> float:
        """
        Kling-Gupta Efficiency (Gupta et al. 2009).
        KGE = 1  →  perfect. Components: r (correlation), α (variability), β (bias).
        """
        obs_mean = self.y_true.mean()
        sim_mean = self.y_pred.mean()
        obs_std  = self.y_true.std()
        sim_std  = self.y_pred.std()

        if obs_std == 0 or sim_std == 0 or obs_mean == 0:
            return float("nan")

        r = float(np.corrcoef(self.y_true, self.y_pred)[0, 1])
        alpha = sim_std / obs_std
        beta  = sim_mean / obs_mean
        return float(1.0 - np.sqrt((r - 1) ** 2 + (alpha - 1) ** 2 + (beta - 1) ** 2))

    def pbias(self) -> float:
        """
        Percent Bias = 100 × Σ(obs − sim) / Σ(obs).
        Positive = under-prediction, negative = over-prediction (SWAT convention).
        """
        total_obs = self.y_true.sum()
        if total_obs == 0:
            return float("nan")
        return float(100.0 * (self.y_true - self.y_pred).sum() / total_obs)

    # ── Threshold / dichotomous scores ───────────────────────────────────────

    def threshold_scores(self, threshold_mm: float, label: str = "") -> ThresholdScores:
        obs_bin = (self.y_true >= threshold_mm).astype(int)
        pred_bin = (self.y_pred >= threshold_mm).astype(int)

        tp = int(((obs_bin == 1) & (pred_bin == 1)).sum())
        fp = int(((obs_bin == 0) & (pred_bin == 1)).sum())
        fn = int(((obs_bin == 1) & (pred_bin == 0)).sum())

        pod = tp / (tp + fn) if (tp + fn) > 0 else float("nan")
        far = fp / (tp + fp) if (tp + fp) > 0 else float("nan")
        csi = tp / (tp + fp + fn) if (tp + fp + fn) > 0 else float("nan")

        return ThresholdScores(
            threshold_mm=threshold_mm,
            label=label or f">={threshold_mm}mm",
            pod=round(pod, 4) if not np.isnan(pod) else float("nan"),
            far=round(far, 4) if not np.isnan(far) else float("nan"),
            csi=round(csi, 4) if not np.isnan(csi) else float("nan"),
            n_events=int(obs_bin.sum()),
        )

    # ── Summary ──────────────────────────────────────────────────────────────

    def evaluate(self) -> RegressionResult:
        thresh_scores = [
            asdict(self.threshold_scores(v, k))
            for k, v in self.thresholds.items()
        ]
        return RegressionResult(
            rmse=round(self.rmse(), 4),
            mae=round(self.mae(), 4),
            r2=round(self.r2(), 4),
            mape=round(self.mape(), 4),
            bias=round(self.bias(), 4),
            nse=round(self.nse(), 4),
            kge=round(self.kge(), 4),
            pbias=round(self.pbias(), 4),
            n_samples=int(len(self.y_true)),
            threshold_scores=thresh_scores,
        )

    def summary(self, verbose: bool = True) -> RegressionResult:
        result = self.evaluate()
        if verbose:
            print("=" * 56)
            print(f"  Regression Metrics  (n={result.n_samples:,})")
            print("=" * 56)
            print(f"  RMSE  : {result.rmse:>10.4f}  mm")
            print(f"  MAE   : {result.mae:>10.4f}  mm")
            print(f"  R²    : {result.r2:>10.4f}")
            print(f"  MAPE  : {result.mape:>10.4f}  %")
            print(f"  Bias  : {result.bias:>+10.4f}  mm  (+ = over-predict)")
            print("-" * 56)
            print(f"  NSE   : {result.nse:>10.4f}  (>0.6 = good, >0.75 = excellent)")
            print(f"  KGE   : {result.kge:>10.4f}  (>0.75 = good)")
            print(f"  PBIAS : {result.pbias:>+10.4f}  %  (|<10| = very good)")
            print("-" * 56)
            print("  IMD Threshold Scores (CSI / POD / FAR):")
            for ts in result.threshold_scores:
                print(
                    f"    {ts['label']:25s}  CSI={ts['csi']:.3f}  "
                    f"POD={ts['pod']:.3f}  FAR={ts['far']:.3f}  "
                    f"(n_events={ts['n_events']})"
                )
            print("=" * 56)
        return result

    def save(self, output_path: str | Path) -> None:
        """Persist metrics to a JSON file."""
        result = self.evaluate()
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w") as f:
            f.write(result.to_json())
        print(f"[RegressionEvaluator] Saved metrics → {out}")


# ── CLI entrypoint ───────────────────────────────────────────────────────────

def _cli() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Evaluate regression predictions against ground-truth labels."
    )
    parser.add_argument("--true",  required=True, help="CSV file with ground-truth column")
    parser.add_argument("--pred",  required=True, help="CSV file with prediction column")
    parser.add_argument("--true-col",  default=None, help="Column name in --true file (default: first col)")
    parser.add_argument("--pred-col",  default=None, help="Column name in --pred file (default: first col)")
    parser.add_argument("--output", default=None, help="Path to save JSON metrics (optional)")
    args = parser.parse_args()

    y_true_df = pd.read_csv(args.true)
    y_pred_df = pd.read_csv(args.pred)

    y_true = y_true_df.iloc[:, 0] if args.true_col is None else y_true_df[args.true_col]
    y_pred = y_pred_df.iloc[:, 0] if args.pred_col is None else y_pred_df[args.pred_col]

    ev = RegressionEvaluator(y_true, y_pred)
    result = ev.summary(verbose=True)

    if args.output:
        ev.save(args.output)


if __name__ == "__main__":
    _cli()
