"""
evaluation/classification_metrics.py
─────────────────────────────────────────────────────────────────────────────
Classification evaluation utilities.

Handles both:
  - Binary classification (e.g. cloudburst flag: 0/1, landslide flag)
  - Multiclass classification (e.g. IMD rainfall category: 0-5)

Metrics
-------
Binary:
  accuracy, precision, recall, F1, ROC-AUC, PR-AUC,
  confusion matrix, Matthews Correlation Coefficient (MCC),
  G-mean (geometric mean of sensitivity and specificity).

Multiclass:
  accuracy, macro/weighted precision, recall, F1, ROC-AUC (OvR),
  per-class breakdown, confusion matrix.

Usage
-----
    from evaluation.classification_metrics import ClassificationEvaluator
    ev = ClassificationEvaluator(y_true, y_pred, probas=y_proba, task="binary")
    print(ev.summary())
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional, Sequence

import numpy as np
import pandas as pd

try:
    from sklearn.metrics import (
        accuracy_score,
        auc,
        average_precision_score,
        confusion_matrix,
        f1_score,
        matthews_corrcoef,
        precision_score,
        recall_score,
        roc_auc_score,
        roc_curve,
    )
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "scikit-learn is required for ClassificationEvaluator. "
        "Install it with: pip install scikit-learn"
    ) from exc


# ── Result dataclasses ───────────────────────────────────────────────────────

@dataclass
class BinaryResult:
    accuracy: float
    precision: float
    recall: float          # = sensitivity = POD
    f1: float
    specificity: float     # = 1 - FAR
    mcc: float             # Matthews Correlation Coefficient
    g_mean: float          # geometric mean of sensitivity & specificity
    roc_auc: float
    pr_auc: float
    confusion_matrix: list[list[int]]
    n_samples: int
    n_positive: int

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


@dataclass
class MulticlassResult:
    accuracy: float
    macro_precision: float
    macro_recall: float
    macro_f1: float
    weighted_f1: float
    roc_auc_ovr: float          # OvR macro average
    confusion_matrix: list[list[int]]
    per_class: list[dict]       # per-label breakdown
    n_samples: int
    n_classes: int

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


# ── Core evaluator ───────────────────────────────────────────────────────────

class ClassificationEvaluator:
    """
    Compute classification metrics for hazard prediction tasks.

    Parameters
    ----------
    y_true  : array-like, ground-truth integer labels
    y_pred  : array-like, predicted integer labels
    probas  : array-like, shape (n,) for binary or (n, n_classes) for multiclass
    task    : "binary" | "multiclass"
    labels  : optional list of label names for confusion-matrix display
    """

    def __init__(
        self,
        y_true: "np.ndarray | pd.Series | Sequence",
        y_pred: "np.ndarray | pd.Series | Sequence",
        probas: Optional["np.ndarray | pd.DataFrame"] = None,
        task: str = "binary",
        labels: Optional[list] = None,
    ) -> None:
        self.y_true  = np.asarray(y_true).ravel()
        self.y_pred  = np.asarray(y_pred).ravel()
        self.probas  = np.asarray(probas) if probas is not None else None
        self.task    = task.lower()
        self.labels  = labels

        if self.task not in ("binary", "multiclass"):
            raise ValueError("task must be 'binary' or 'multiclass'")

    # ── Binary ───────────────────────────────────────────────────────────────

    def _binary(self) -> BinaryResult:
        yt, yp = self.y_true, self.y_pred

        acc       = float(accuracy_score(yt, yp))
        prec      = float(precision_score(yt, yp, zero_division=0))
        rec       = float(recall_score(yt, yp, zero_division=0))
        f1        = float(f1_score(yt, yp, zero_division=0))
        mcc       = float(matthews_corrcoef(yt, yp))

        cm        = confusion_matrix(yt, yp)
        tn, fp, fn, tp = cm.ravel() if cm.size == 4 else (0, 0, 0, 0)
        specificity = float(tn / (tn + fp)) if (tn + fp) > 0 else float("nan")
        g_mean      = float(np.sqrt(rec * specificity)) if not np.isnan(specificity) else float("nan")

        # ROC-AUC / PR-AUC — need probabilities for positive class
        roc_auc_val = float("nan")
        pr_auc_val  = float("nan")
        if self.probas is not None:
            proba_pos = self.probas[:, 1] if self.probas.ndim == 2 else self.probas.ravel()
            try:
                roc_auc_val = float(roc_auc_score(yt, proba_pos))
                pr_auc_val  = float(average_precision_score(yt, proba_pos))
            except Exception:
                pass

        return BinaryResult(
            accuracy=round(acc, 4),
            precision=round(prec, 4),
            recall=round(rec, 4),
            specificity=round(specificity, 4) if not np.isnan(specificity) else float("nan"),
            f1=round(f1, 4),
            mcc=round(mcc, 4),
            g_mean=round(g_mean, 4) if not np.isnan(g_mean) else float("nan"),
            roc_auc=round(roc_auc_val, 4) if not np.isnan(roc_auc_val) else float("nan"),
            pr_auc=round(pr_auc_val, 4)   if not np.isnan(pr_auc_val)  else float("nan"),
            confusion_matrix=cm.tolist(),
            n_samples=int(len(yt)),
            n_positive=int(yt.sum()),
        )

    # ── Multiclass ───────────────────────────────────────────────────────────

    def _multiclass(self) -> MulticlassResult:
        yt, yp = self.y_true, self.y_pred
        classes = np.unique(yt)
        n_cls   = len(classes)

        acc       = float(accuracy_score(yt, yp))
        macro_p   = float(precision_score(yt, yp, average="macro", zero_division=0))
        macro_r   = float(recall_score(yt, yp, average="macro", zero_division=0))
        macro_f1  = float(f1_score(yt, yp, average="macro", zero_division=0))
        weighted_f1 = float(f1_score(yt, yp, average="weighted", zero_division=0))

        roc_auc_val = float("nan")
        if self.probas is not None and self.probas.ndim == 2:
            try:
                roc_auc_val = float(
                    roc_auc_score(yt, self.probas, multi_class="ovr", average="macro")
                )
            except Exception:
                pass

        cm = confusion_matrix(yt, yp).tolist()

        per_class = []
        for cls in classes:
            binary_true = (yt == cls).astype(int)
            binary_pred = (yp == cls).astype(int)
            label_name = self.labels[cls] if self.labels and cls < len(self.labels) else str(cls)
            per_class.append({
                "label":     label_name,
                "precision": round(float(precision_score(binary_true, binary_pred, zero_division=0)), 4),
                "recall":    round(float(recall_score(binary_true, binary_pred, zero_division=0)), 4),
                "f1":        round(float(f1_score(binary_true, binary_pred, zero_division=0)), 4),
                "support":   int(binary_true.sum()),
            })

        return MulticlassResult(
            accuracy=round(acc, 4),
            macro_precision=round(macro_p, 4),
            macro_recall=round(macro_r, 4),
            macro_f1=round(macro_f1, 4),
            weighted_f1=round(weighted_f1, 4),
            roc_auc_ovr=round(roc_auc_val, 4) if not np.isnan(roc_auc_val) else float("nan"),
            confusion_matrix=cm,
            per_class=per_class,
            n_samples=int(len(yt)),
            n_classes=n_cls,
        )

    # ── Unified ──────────────────────────────────────────────────────────────

    def evaluate(self) -> "BinaryResult | MulticlassResult":
        if self.task == "binary":
            return self._binary()
        return self._multiclass()

    def summary(self, verbose: bool = True) -> "BinaryResult | MulticlassResult":
        result = self.evaluate()
        if verbose:
            if isinstance(result, BinaryResult):
                print("=" * 56)
                print(f"  Binary Classification Metrics  (n={result.n_samples:,}, positives={result.n_positive:,})")
                print("=" * 56)
                print(f"  Accuracy    : {result.accuracy:.4f}")
                print(f"  Precision   : {result.precision:.4f}")
                print(f"  Recall(POD) : {result.recall:.4f}")
                print(f"  Specificity : {result.specificity:.4f}")
                print(f"  F1-Score    : {result.f1:.4f}")
                print(f"  MCC         : {result.mcc:.4f}")
                print(f"  G-Mean      : {result.g_mean:.4f}")
                print(f"  ROC-AUC     : {result.roc_auc:.4f}")
                print(f"  PR-AUC      : {result.pr_auc:.4f}")
                print(f"  Confusion Matrix: TN={result.confusion_matrix[0][0]}  FP={result.confusion_matrix[0][1]}  FN={result.confusion_matrix[1][0]}  TP={result.confusion_matrix[1][1]}")
                print("=" * 56)
            else:
                print("=" * 56)
                print(f"  Multiclass Classification Metrics  (n={result.n_samples:,}, classes={result.n_classes})")
                print("=" * 56)
                print(f"  Accuracy        : {result.accuracy:.4f}")
                print(f"  Macro Precision : {result.macro_precision:.4f}")
                print(f"  Macro Recall    : {result.macro_recall:.4f}")
                print(f"  Macro F1        : {result.macro_f1:.4f}")
                print(f"  Weighted F1     : {result.weighted_f1:.4f}")
                print(f"  ROC-AUC (OvR)  : {result.roc_auc_ovr:.4f}")
                print("-" * 56)
                print("  Per-class breakdown:")
                for pc in result.per_class:
                    print(f"    {pc['label']:25s}  F1={pc['f1']:.3f}  P={pc['precision']:.3f}  R={pc['recall']:.3f}  (n={pc['support']})")
                print("=" * 56)
        return result

    def save(self, output_path: str | Path) -> None:
        result = self.evaluate()
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w") as f:
            json.dump(result.to_dict(), f, indent=2)
        print(f"[ClassificationEvaluator] Saved metrics → {out}")


# ── CLI ──────────────────────────────────────────────────────────────────────

def _cli() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Evaluate classification predictions.")
    parser.add_argument("--true",  required=True)
    parser.add_argument("--pred",  required=True)
    parser.add_argument("--probas", default=None, help="CSV with probability columns")
    parser.add_argument("--task",  default="binary", choices=["binary", "multiclass"])
    parser.add_argument("--true-col",  default=None)
    parser.add_argument("--pred-col",  default=None)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    y_true = pd.read_csv(args.true)
    y_true = y_true.iloc[:, 0] if args.true_col is None else y_true[args.true_col]

    y_pred = pd.read_csv(args.pred)
    y_pred = y_pred.iloc[:, 0] if args.pred_col is None else y_pred[args.pred_col]

    probas = None
    if args.probas:
        probas = pd.read_csv(args.probas).values

    ev = ClassificationEvaluator(y_true, y_pred, probas=probas, task=args.task)
    result = ev.summary(verbose=True)

    if args.output:
        ev.save(args.output)


if __name__ == "__main__":
    _cli()
