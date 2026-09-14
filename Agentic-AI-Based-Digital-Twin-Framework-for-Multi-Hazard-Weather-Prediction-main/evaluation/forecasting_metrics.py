"""
evaluation/forecasting_metrics.py
─────────────────────────────────────────────────────────────────────────────
Time-series / forecasting evaluation utilities.

Unlike regression_metrics.py (which treats predictions as independent samples),
this module accounts for temporal structure:

Metrics
-------
  - Rolling-window RMSE / MAE at multiple lead times
  - Skill Score vs. climatological (persistence / climatology) baseline
  - Lead-time RMSE degradation curve (how fast does skill decay with horizon?)
  - Temporal correlation (pattern correlation, Pearson r across time)
  - Mean Phase Error (lag at which cross-correlation is maximised)
  - Peak-flow / peak-rainfall hit: did the model capture the timing and
    magnitude of the top-N events?

Usage
─────
    from evaluation.forecasting_metrics import ForecastingEvaluator
    ev = ForecastingEvaluator(observations, forecasts, timestamps=timestamps)
    ev.summary()
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional, Sequence

import numpy as np
import pandas as pd


# ── Result dataclasses ───────────────────────────────────────────────────────

@dataclass
class LeadTimeScore:
    lead_hours: int
    rmse: float
    mae: float
    skill_vs_persistence: float   # positive = better than persistence, max 1
    skill_vs_climatology: float   # positive = better than climatology mean


@dataclass
class PeakEventScore:
    """Did the forecast capture the top-N extreme events?"""
    top_n: int
    hit_rate: float              # fraction of top-N obs events with a top-N forecast within ±lead_hours
    magnitude_bias_pct: float    # (pred_peak − obs_peak) / obs_peak × 100


@dataclass
class ForecastingResult:
    overall_rmse: float
    overall_mae: float
    temporal_r: float             # Pearson correlation across time
    phase_error_hours: float      # lag at max cross-correlation (negative = forecast leads)
    skill_vs_persistence: float
    skill_vs_climatology: float
    lead_time_scores: list[dict]
    peak_event_scores: list[dict]
    n_timesteps: int

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _rmse(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.sqrt(np.mean((a - b) ** 2)))


def _mae(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.mean(np.abs(a - b)))


def _skill_score(forecast_rmse: float, reference_rmse: float) -> float:
    """Skill = 1 − (RMSE_forecast / RMSE_reference). Range: (−∞, 1]."""
    if reference_rmse == 0:
        return float("nan")
    return float(1.0 - forecast_rmse / reference_rmse)


# ── Core evaluator ───────────────────────────────────────────────────────────

class ForecastingEvaluator:
    """
    Evaluate time-series forecasts against observations.

    Parameters
    ----------
    observations : array-like, shape (T,)
        Ground-truth time series (e.g. hourly rainfall observations).
    forecasts : array-like, shape (T,) or (T, H)
        If 1-D: treated as single-horizon predictions aligned with observations.
        If 2-D: each column is a different lead-time horizon (col 0 = +1h, col 1 = +2h …).
    timestamps : pd.DatetimeIndex or array-like, optional
        If provided, used for phase-error computation and rolling windows.
    lead_hours_to_eval : list[int], optional
        Which lead-hour columns to evaluate when forecasts is 2-D.
    top_n_events : int
        Number of top extreme events to evaluate peak-capture skill for.
    """

    def __init__(
        self,
        observations: "np.ndarray | pd.Series | Sequence",
        forecasts: "np.ndarray | pd.Series | Sequence",
        timestamps: Optional["pd.DatetimeIndex | Sequence"] = None,
        lead_hours_to_eval: Optional[list] = None,
        top_n_events: int = 10,
    ) -> None:
        self.obs = np.asarray(observations, dtype=float).ravel()
        self.fct = np.asarray(forecasts, dtype=float)
        if self.fct.ndim == 1:
            self.fct = self.fct.reshape(-1, 1)  # shape (T, 1)

        self.T, self.H = self.fct.shape
        if len(self.obs) != self.T:
            raise ValueError(f"Observations length {len(self.obs)} != forecasts rows {self.T}")

        self.timestamps = timestamps
        self.lead_hours = lead_hours_to_eval or list(range(1, self.H + 1))
        self.top_n_events = top_n_events

    # ── Baseline references ──────────────────────────────────────────────────

    def _persistence_baseline(self) -> np.ndarray:
        """Persistence: predict obs[t] = obs[t-1]."""
        base = np.empty_like(self.obs)
        base[0] = self.obs[0]
        base[1:] = self.obs[:-1]
        return base

    def _climatology_baseline(self) -> np.ndarray:
        """Climatology: always predict the mean of the observed series."""
        return np.full_like(self.obs, self.obs.mean())

    # ── Phase error ──────────────────────────────────────────────────────────

    def _phase_error_hours(self, fct_col: np.ndarray, max_lag: int = 24) -> float:
        """
        Find the lag (in hours) where cross-correlation is maximised.
        Negative lag → forecast leads observations (model anticipates event).
        """
        obs_centered = self.obs - self.obs.mean()
        fct_centered = fct_col - fct_col.mean()
        lags = range(-max_lag, max_lag + 1)
        corrs = []
        for lag in lags:
            if lag < 0:
                cc = np.corrcoef(obs_centered[-lag:], fct_centered[:lag])[0, 1]
            elif lag > 0:
                cc = np.corrcoef(obs_centered[:-lag], fct_centered[lag:])[0, 1]
            else:
                cc = np.corrcoef(obs_centered, fct_centered)[0, 1]
            corrs.append(0.0 if np.isnan(cc) else cc)
        best_lag_idx = int(np.argmax(corrs))
        return float(list(lags)[best_lag_idx])

    # ── Peak-event capture ───────────────────────────────────────────────────

    def _peak_event_score(self, fct_col: np.ndarray, lead_hours: int = 6) -> PeakEventScore:
        n = min(self.top_n_events, len(self.obs))
        top_obs_idx = np.argsort(self.obs)[-n:]

        hit = 0
        mag_errors = []
        for idx in top_obs_idx:
            window_start = max(0, idx - lead_hours)
            window_end   = min(self.T, idx + lead_hours + 1)
            window_fct   = fct_col[window_start:window_end]
            top_fct_idx  = np.argsort(fct_col)[-n:]
            overlap = set(np.arange(window_start, window_end)) & set(top_fct_idx)
            if overlap:
                hit += 1
            mag_errors.append(float(fct_col[idx] - self.obs[idx]))

        hit_rate = hit / n if n > 0 else float("nan")
        obs_peak_mean = self.obs[top_obs_idx].mean()
        mag_bias_pct = float(np.mean(mag_errors) / obs_peak_mean * 100) if obs_peak_mean != 0 else float("nan")

        return PeakEventScore(
            top_n=n,
            hit_rate=round(hit_rate, 4),
            magnitude_bias_pct=round(mag_bias_pct, 4),
        )

    # ── Per-lead evaluation ──────────────────────────────────────────────────

    def _lead_time_score(self, h_idx: int, lead_h: int) -> LeadTimeScore:
        fct_col = self.fct[:, h_idx]
        pers    = self._persistence_baseline()
        clim    = self._climatology_baseline()

        f_rmse = _rmse(fct_col, self.obs)
        f_mae  = _mae(fct_col, self.obs)
        skill_p = _skill_score(f_rmse, _rmse(pers, self.obs))
        skill_c = _skill_score(f_rmse, _rmse(clim, self.obs))

        return LeadTimeScore(
            lead_hours=lead_h,
            rmse=round(f_rmse, 4),
            mae=round(f_mae, 4),
            skill_vs_persistence=round(skill_p, 4) if not np.isnan(skill_p) else float("nan"),
            skill_vs_climatology=round(skill_c, 4) if not np.isnan(skill_c) else float("nan"),
        )

    # ── Main evaluate ────────────────────────────────────────────────────────

    def evaluate(self) -> ForecastingResult:
        # Use first column (lead = +1h, or the only column for single-horizon)
        fct_primary = self.fct[:, 0]
        pers = self._persistence_baseline()
        clim = self._climatology_baseline()

        overall_rmse = _rmse(fct_primary, self.obs)
        overall_mae  = _mae(fct_primary,  self.obs)

        r_val = float(np.corrcoef(self.obs, fct_primary)[0, 1])
        phase = self._phase_error_hours(fct_primary)

        skill_p = _skill_score(overall_rmse, _rmse(pers, self.obs))
        skill_c = _skill_score(overall_rmse, _rmse(clim, self.obs))

        lead_scores = []
        peak_scores = []
        for h_idx, lead_h in enumerate(self.lead_hours):
            if h_idx < self.H:
                lt = self._lead_time_score(h_idx, lead_h)
                pk = self._peak_event_score(self.fct[:, h_idx], lead_hours=lead_h)
                lead_scores.append(asdict(lt))
                peak_scores.append(asdict(pk))

        return ForecastingResult(
            overall_rmse=round(overall_rmse, 4),
            overall_mae=round(overall_mae,  4),
            temporal_r=round(r_val, 4),
            phase_error_hours=round(phase, 1),
            skill_vs_persistence=round(skill_p, 4) if not np.isnan(skill_p) else float("nan"),
            skill_vs_climatology=round(skill_c, 4) if not np.isnan(skill_c) else float("nan"),
            lead_time_scores=lead_scores,
            peak_event_scores=peak_scores,
            n_timesteps=self.T,
        )

    def summary(self, verbose: bool = True) -> ForecastingResult:
        result = self.evaluate()
        if verbose:
            print("=" * 64)
            print(f"  Forecasting Metrics  (T={result.n_timesteps:,})")
            print("=" * 64)
            print(f"  RMSE (lead +1h)       : {result.overall_rmse:.4f} mm")
            print(f"  MAE  (lead +1h)       : {result.overall_mae:.4f}  mm")
            print(f"  Temporal correlation  : {result.temporal_r:.4f}")
            print(f"  Phase error           : {result.phase_error_hours:+.1f} h  "
                  f"({'model leads' if result.phase_error_hours < 0 else 'model lags'})")
            print(f"  Skill vs persistence  : {result.skill_vs_persistence:.4f}  (>0 = better than naive)")
            print(f"  Skill vs climatology  : {result.skill_vs_climatology:.4f}  (>0 = better than mean)")
            if len(result.lead_time_scores) > 1:
                print("-" * 64)
                print("  Lead-time degradation:")
                for lt in result.lead_time_scores:
                    print(f"    +{lt['lead_hours']:2d}h  RMSE={lt['rmse']:.4f}  "
                          f"Skill_p={lt['skill_vs_persistence']:.4f}  "
                          f"Skill_c={lt['skill_vs_climatology']:.4f}")
            print("-" * 64)
            print(f"  Peak event capture (top {result.peak_event_scores[0]['top_n'] if result.peak_event_scores else 'N'}):")
            for pk in result.peak_event_scores:
                print(f"    +{pk.get('top_n','?')} events  Hit={pk['hit_rate']:.3f}  "
                      f"MagBias={pk['magnitude_bias_pct']:+.2f}%")
            print("=" * 64)
        return result

    def save(self, output_path: str | Path) -> None:
        result = self.evaluate()
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w") as f:
            f.write(result.to_json())
        print(f"[ForecastingEvaluator] Saved metrics → {out}")


# ── CLI ──────────────────────────────────────────────────────────────────────

def _cli() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Evaluate time-series forecasts.")
    parser.add_argument("--obs",  required=True, help="CSV with observed values")
    parser.add_argument("--fct",  required=True, help="CSV with forecast values (multi-column = multi-horizon)")
    parser.add_argument("--obs-col", default=None)
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    obs_df = pd.read_csv(args.obs)
    obs = obs_df.iloc[:, 0] if args.obs_col is None else obs_df[args.obs_col]
    fct = pd.read_csv(args.fct).values

    ev = ForecastingEvaluator(obs, fct, top_n_events=args.top_n)
    result = ev.summary(verbose=True)

    if args.output:
        ev.save(args.output)


if __name__ == "__main__":
    _cli()
