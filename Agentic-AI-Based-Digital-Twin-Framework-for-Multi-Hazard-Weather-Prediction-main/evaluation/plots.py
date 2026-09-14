"""
evaluation/plots.py
─────────────────────────────────────────────────────────────────────────────
Matplotlib / seaborn visualisation helpers for model evaluation.

All functions:
  • Return the figure object (so callers can save or show as needed)
  • Accept an optional `ax` / `axes` argument for embedding in subplots
  • Save to disk if `output_path` is provided

Available plots
───────────────
  plot_residuals()          → scatter + histogram of (pred − obs)
  plot_confusion_matrix()   → annotated heatmap
  plot_roc_curve()          → ROC with AUC annotation
  plot_model_comparison()   → horizontal bar chart of metric across models
  plot_lead_degradation()   → RMSE vs lead time (single or multiple models)
  plot_taylor_diagram()     → Taylor diagram (correlation, std ratio, RMSE)
  plot_imd_category_rates() → CSI / POD / FAR grouped bar chart by IMD tier
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence

import numpy as np

try:
    import matplotlib
    matplotlib.use("Agg")   # non-interactive backend — safe for server / CI
    import matplotlib.pyplot as plt
    import matplotlib.ticker as ticker
except ImportError as exc:
    raise ImportError(
        "matplotlib is required for plots. Install with: pip install matplotlib"
    ) from exc

try:
    import seaborn as sns
    _HAS_SEABORN = True
except ImportError:
    _HAS_SEABORN = False


# ── Style helper ─────────────────────────────────────────────────────────────

def _apply_style() -> None:
    """Apply a clean dark-ish research style."""
    plt.rcParams.update({
        "figure.facecolor":  "#0f1117",
        "axes.facecolor":    "#1a1d27",
        "axes.edgecolor":    "#333650",
        "axes.labelcolor":   "#c8cce0",
        "axes.titlecolor":   "#e8eaf6",
        "xtick.color":       "#888aaa",
        "ytick.color":       "#888aaa",
        "grid.color":        "#252840",
        "grid.linestyle":    "--",
        "grid.alpha":        0.5,
        "text.color":        "#c8cce0",
        "font.family":       "sans-serif",
        "font.size":         10,
        "axes.titlesize":    12,
        "axes.labelsize":    10,
        "legend.facecolor":  "#1a1d27",
        "legend.edgecolor":  "#333650",
        "legend.fontsize":   9,
    })


_ACCENT = ["#7b9cff", "#ff7b7b", "#7bffb5", "#ffda7b", "#da7bff", "#7bd9ff"]


# ── 1. Residuals ─────────────────────────────────────────────────────────────

def plot_residuals(
    y_true: "np.ndarray | Sequence",
    y_pred: "np.ndarray | Sequence",
    model_name: str = "",
    output_path: Optional[str | Path] = None,
) -> "plt.Figure":
    """
    Two-panel residual plot:
      Left:  Scatter of observed vs predicted (+ ideal diagonal)
      Right: Histogram of residuals (pred − obs)
    """
    _apply_style()
    y_true = np.asarray(y_true).ravel()
    y_pred = np.asarray(y_pred).ravel()
    residuals = y_pred - y_true

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    fig.suptitle(f"Residual Analysis  —  {model_name}", fontsize=13, fontweight="bold")

    # Scatter
    ax1.scatter(y_true, y_pred, alpha=0.35, s=12, color=_ACCENT[0], label="Predictions")
    lims = [min(y_true.min(), y_pred.min()), max(y_true.max(), y_pred.max())]
    ax1.plot(lims, lims, color="#ff7b7b", linewidth=1.5, linestyle="--", label="Perfect fit")
    ax1.set_xlabel("Observed (mm)")
    ax1.set_ylabel("Predicted (mm)")
    ax1.set_title("Observed vs Predicted")
    ax1.legend()
    ax1.grid(True)

    # Histogram
    ax2.hist(residuals, bins=50, color=_ACCENT[0], edgecolor="#0f1117", alpha=0.85)
    ax2.axvline(0, color="#ff7b7b", linewidth=1.5, linestyle="--", label="Zero bias")
    ax2.axvline(residuals.mean(), color="#ffda7b", linewidth=1.2, linestyle=":",
                label=f"Mean bias = {residuals.mean():.2f} mm")
    ax2.set_xlabel("Residual (pred − obs) mm")
    ax2.set_ylabel("Count")
    ax2.set_title("Residual Distribution")
    ax2.legend()
    ax2.grid(True)

    fig.tight_layout()
    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(output_path), dpi=150, bbox_inches="tight")
        print(f"[plots] Residuals saved → {output_path}")
    return fig


# ── 2. Confusion matrix ───────────────────────────────────────────────────────

def plot_confusion_matrix(
    cm: "np.ndarray | list",
    class_names: Optional[list] = None,
    normalize: bool = True,
    model_name: str = "",
    output_path: Optional[str | Path] = None,
) -> "plt.Figure":
    """Annotated confusion-matrix heatmap."""
    _apply_style()
    cm = np.asarray(cm)
    n = cm.shape[0]
    if class_names is None:
        class_names = [str(i) for i in range(n)]

    if normalize:
        row_sums = cm.sum(axis=1, keepdims=True)
        cm_plot = np.where(row_sums > 0, cm / row_sums, 0.0)
        fmt = ".2f"
        title_sfx = " (normalised)"
    else:
        cm_plot = cm
        fmt = "d"
        title_sfx = ""

    fig, ax = plt.subplots(figsize=(max(5, n), max(4, n - 1)))
    cmap = "Blues" if not _HAS_SEABORN else sns.color_palette("Blues_r", as_cmap=True)

    im = ax.imshow(cm_plot, cmap="Blues", vmin=0, vmax=1 if normalize else None)
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)

    ax.set_xticks(range(n))
    ax.set_yticks(range(n))
    ax.set_xticklabels(class_names, rotation=45, ha="right")
    ax.set_yticklabels(class_names)
    ax.set_xlabel("Predicted label")
    ax.set_ylabel("True label")
    ax.set_title(f"Confusion Matrix{title_sfx}  —  {model_name}")

    thresh = cm_plot.max() / 2
    for i in range(n):
        for j in range(n):
            val = f"{cm_plot[i, j]:{fmt}}"
            ax.text(j, i, val, ha="center", va="center",
                    color="white" if cm_plot[i, j] > thresh else "#c8cce0", fontsize=9)

    fig.tight_layout()
    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(output_path), dpi=150, bbox_inches="tight")
        print(f"[plots] Confusion matrix saved → {output_path}")
    return fig


# ── 3. ROC curve ─────────────────────────────────────────────────────────────

def plot_roc_curve(
    y_true: "np.ndarray | Sequence",
    probas: "np.ndarray | Sequence",
    model_name: str = "",
    output_path: Optional[str | Path] = None,
) -> "plt.Figure":
    """ROC curve with AUC annotation."""
    from sklearn.metrics import roc_auc_score, roc_curve

    _apply_style()
    y_true = np.asarray(y_true).ravel()
    probas = np.asarray(probas).ravel()

    fpr, tpr, _ = roc_curve(y_true, probas)
    auc_val = roc_auc_score(y_true, probas)

    fig, ax = plt.subplots(figsize=(6, 5))
    ax.plot(fpr, tpr, color=_ACCENT[0], linewidth=2, label=f"ROC curve (AUC = {auc_val:.4f})")
    ax.plot([0, 1], [0, 1], color="#888aaa", linewidth=1.2, linestyle="--", label="Random classifier")
    ax.set_xlabel("False Positive Rate")
    ax.set_ylabel("True Positive Rate (Recall)")
    ax.set_title(f"ROC Curve  —  {model_name}")
    ax.legend(loc="lower right")
    ax.grid(True)
    fig.tight_layout()

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(output_path), dpi=150, bbox_inches="tight")
        print(f"[plots] ROC curve saved → {output_path}")
    return fig


# ── 4. Model comparison bar chart ─────────────────────────────────────────────

def plot_model_comparison(
    model_names: list,
    metric_values: list,
    metric_label: str = "RMSE (mm)",
    higher_is_better: bool = False,
    title: str = "Model Benchmark Comparison",
    output_path: Optional[str | Path] = None,
) -> "plt.Figure":
    """Horizontal bar chart ranking models by a single metric."""
    _apply_style()
    n = len(model_names)
    vals = list(metric_values)
    names = list(model_names)

    # Sort: best at top
    pairs = sorted(zip(vals, names), reverse=higher_is_better)
    vals_sorted  = [p[0] for p in pairs]
    names_sorted = [p[1] for p in pairs]

    colors = [_ACCENT[0] if i == 0 else "#4a5078" for i in range(n)]

    fig, ax = plt.subplots(figsize=(9, max(3, n * 0.55 + 1.5)))
    bars = ax.barh(range(n), vals_sorted, color=colors, height=0.6, edgecolor="#0f1117")
    ax.set_yticks(range(n))
    ax.set_yticklabels(names_sorted, fontsize=9)
    ax.set_xlabel(metric_label)
    ax.set_title(title)
    ax.grid(True, axis="x")
    ax.invert_yaxis()

    for i, (bar, val) in enumerate(zip(bars, vals_sorted)):
        ax.text(bar.get_width() + max(abs(v) for v in vals_sorted) * 0.01,
                bar.get_y() + bar.get_height() / 2,
                f"{val:.4f}", va="center", fontsize=8,
                color="#ffda7b" if i == 0 else "#c8cce0")

    ax.text(0.98, 0.02, "🏆 Best" if higher_is_better else "⬇ Lower is better",
            transform=ax.transAxes, ha="right", va="bottom",
            fontsize=8, color="#888aaa")

    fig.tight_layout()
    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(output_path), dpi=150, bbox_inches="tight")
        print(f"[plots] Model comparison saved → {output_path}")
    return fig


# ── 5. Lead-time degradation ──────────────────────────────────────────────────

def plot_lead_degradation(
    lead_hours: list,
    rmse_series: "dict | list",
    ylabel: str = "RMSE (mm)",
    title: str = "Forecast Skill vs Lead Time",
    output_path: Optional[str | Path] = None,
) -> "plt.Figure":
    """
    Plot RMSE (or other metric) vs lead time.
    rmse_series can be:
      - list: single model
      - dict[model_name, list]: multiple models
    """
    _apply_style()
    fig, ax = plt.subplots(figsize=(9, 5))

    if isinstance(rmse_series, dict):
        for i, (name, vals) in enumerate(rmse_series.items()):
            ax.plot(lead_hours, vals, marker="o", linewidth=2,
                    color=_ACCENT[i % len(_ACCENT)], label=name, markersize=5)
        ax.legend()
    else:
        ax.plot(lead_hours, rmse_series, marker="o", color=_ACCENT[0],
                linewidth=2.5, markersize=6, label="Model")

    ax.set_xlabel("Lead time (hours)")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(True)
    ax.xaxis.set_major_locator(ticker.MaxNLocator(integer=True))

    fig.tight_layout()
    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(output_path), dpi=150, bbox_inches="tight")
        print(f"[plots] Lead degradation saved → {output_path}")
    return fig


# ── 6. Taylor diagram ─────────────────────────────────────────────────────────

def plot_taylor_diagram(
    obs_std: float,
    model_points: list,  # list of dicts: {name, std_ratio, correlation}
    title: str = "Taylor Diagram",
    output_path: Optional[str | Path] = None,
) -> "plt.Figure":
    """
    Simplified Taylor Diagram in polar coords.
    Each model is plotted as (angle=arccos(r), radius=σ_model/σ_obs).
    The observed point is at angle=0, radius=1.
    """
    _apply_style()
    max_std_ratio = max((p.get("std_ratio", 1) for p in model_points), default=1.5) + 0.3

    fig = plt.figure(figsize=(7, 6))
    ax  = fig.add_subplot(111, polar=True)
    ax.set_thetamax(90)
    ax.set_thetalim(0, np.pi / 2)
    ax.set_rlim(0, max_std_ratio)

    # Reference point (observations)
    ax.plot(0, 1.0, marker="*", markersize=14, color="#ffda7b", zorder=5, label="Observed (ref)")

    # Contour arcs for constant RMSE (centred on observed)
    r_contours = np.linspace(0.2, max_std_ratio, 6)
    theta_full  = np.linspace(0, np.pi / 2, 200)
    for rc in r_contours:
        # arc of constant RMSD from obs (centred at (angle=0, r=1))
        # RMSD² = std_m² + std_o² - 2*std_m*std_o*r  →  not trivially a circle in polar
        # Approximate: draw concentric arcs from (0,1)
        x_arc = 1 + rc * np.cos(theta_full)
        y_arc = rc * np.sin(theta_full)
        r_arc = np.sqrt(x_arc**2 + y_arc**2)
        th_arc = np.arctan2(y_arc, x_arc)
        mask = (th_arc >= 0) & (th_arc <= np.pi / 2) & (r_arc <= max_std_ratio)
        ax.plot(th_arc[mask], r_arc[mask], color="#333650", linewidth=0.8, linestyle="--", alpha=0.6)

    # Correlation lines
    for corr in [0.5, 0.7, 0.85, 0.95, 0.99]:
        angle = np.arccos(corr)
        ax.plot([angle, angle], [0, max_std_ratio], color="#333650", linewidth=0.7, alpha=0.5)
        ax.text(angle, max_std_ratio * 1.05, f"r={corr}", ha="center", va="bottom",
                fontsize=7, color="#888aaa", rotation=np.degrees(angle))

    # Model points
    for i, p in enumerate(model_points):
        angle = np.arccos(np.clip(p.get("correlation", 0), -1, 1))
        radius = p.get("std_ratio", 1.0)
        color  = _ACCENT[i % len(_ACCENT)]
        ax.plot(angle, radius, marker="o", markersize=9, color=color, zorder=4, label=p.get("name", f"Model {i+1}"))

    ax.set_rgrids(np.arange(0.5, max_std_ratio, 0.5),
                  labels=[f"{v:.1f}σ" for v in np.arange(0.5, max_std_ratio, 0.5)],
                  fontsize=7, color="#888aaa")
    ax.set_thetagrids([0, 15, 30, 45, 60, 75, 90],
                      labels=["r=1.0", "", "r=0.87", "r=0.71", "r=0.5", "", "r=0"],
                      fontsize=7, color="#888aaa")
    ax.set_title(title, pad=25)
    ax.legend(loc="upper right", bbox_to_anchor=(1.35, 1.0), fontsize=8)

    fig.tight_layout()
    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(output_path), dpi=150, bbox_inches="tight")
        print(f"[plots] Taylor diagram saved → {output_path}")
    return fig


# ── 7. IMD category threshold bar chart ───────────────────────────────────────

def plot_imd_category_rates(
    threshold_scores: list,  # list of dicts with keys: label, csi, pod, far
    model_name: str = "",
    output_path: Optional[str | Path] = None,
) -> "plt.Figure":
    """
    Grouped bar chart showing CSI, POD, and FAR for each IMD rainfall tier.
    """
    _apply_style()
    labels = [ts["label"] for ts in threshold_scores]
    csi_vals = [ts.get("csi", 0) or 0 for ts in threshold_scores]
    pod_vals = [ts.get("pod", 0) or 0 for ts in threshold_scores]
    far_vals = [ts.get("far", 0) or 0 for ts in threshold_scores]

    x = np.arange(len(labels))
    width = 0.25

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(x - width, csi_vals, width, label="CSI (Critical Success Index)", color=_ACCENT[0])
    ax.bar(x,          pod_vals, width, label="POD (Probability of Detection)", color=_ACCENT[2])
    ax.bar(x + width, far_vals, width, label="FAR (False Alarm Ratio)", color=_ACCENT[1])

    ax.set_xlabel("IMD Threshold Tier")
    ax.set_ylabel("Score  [0 – 1]")
    ax.set_title(f"Threshold-Based Scores by IMD Tier  —  {model_name}")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=15, ha="right")
    ax.set_ylim(0, 1.05)
    ax.axhline(0.5, color="#888aaa", linestyle="--", linewidth=0.8, alpha=0.6)
    ax.legend()
    ax.grid(True, axis="y")

    fig.tight_layout()
    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(output_path), dpi=150, bbox_inches="tight")
        print(f"[plots] IMD category rates saved → {output_path}")
    return fig
