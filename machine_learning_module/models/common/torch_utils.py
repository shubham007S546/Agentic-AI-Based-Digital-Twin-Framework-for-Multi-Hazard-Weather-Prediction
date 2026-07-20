"""
Shared PyTorch utilities used by the deep_learning and transformer packages.

Kept in models/common/ (rather than duplicated in each package) since both
LSTM/GRU/TCN and the TFT-Lite transformer need the same three things:
  1. row-aligned sequence windowing (zero-padded so len(output) == len(X),
     which keeps these models drop-in compatible with BaseEvaluator's
     compute_metrics(X, y), which requires predict(X) to return one row per
     input row -- exactly like RandomForest/XGBoost/LightGBM do).
  2. a plain torch Dataset over those windows.
  3. early stopping + device/seed helpers.

Nothing here imports anything from the tabular (sklearn-style) side of the
framework, so importing torch_utils has no effect on random_forest/xgboost/
lightgbm/two_stage_rainfall, and this module can be safely absent (ImportError
on `torch`) unless deep_learning/transformer are actually used.
"""

from __future__ import annotations

import random
from typing import Optional

import numpy as np
import pandas as pd

try:
    import torch
    from torch.utils.data import Dataset
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "The 'torch' package is required for deep_learning / transformer models. "
        "Install it with: pip install torch --index-url https://download.pytorch.org/whl/cpu"
    ) from exc


def get_device(preferred: str = "cpu") -> "torch.device":
    """Resolve 'cpu' | 'cuda' | 'auto' to an available torch.device, falling
    back to CPU if CUDA was requested but is not available."""
    if preferred == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if preferred == "cuda" and not torch.cuda.is_available():
        return torch.device("cpu")
    return torch.device(preferred)


def set_torch_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def build_padded_sequences(
    X: pd.DataFrame,
    sequence_length: int,
    group_ids: Optional[pd.Series] = None,
) -> np.ndarray:
    """
    Build a (n_rows, sequence_length, n_features) tensor of sliding windows,
    ending at (and including) each row -- i.e. output[i] is the window of the
    `sequence_length` rows up to and including row i.

    Row-alignment guarantee: output always has exactly len(X) windows, one
    per input row (unlike naive sliding windowing, which would drop the
    first `sequence_length - 1` rows). Rows that don't have `sequence_length`
    of history yet are LEFT-ZERO-PADDED. If `group_ids` is given, padding/
    windowing restarts at each group boundary (e.g. per weather station /
    district) so a window never bleeds across two unrelated series.
    """
    values = X.to_numpy(dtype=np.float32)
    n_rows, n_features = values.shape
    out = np.zeros((n_rows, sequence_length, n_features), dtype=np.float32)

    if group_ids is None:
        group_arr = np.zeros(n_rows, dtype=np.int64)
    else:
        group_arr = group_ids.to_numpy()

    # process each contiguous group separately so windows never cross groups
    start = 0
    for i in range(1, n_rows + 1):
        if i == n_rows or group_arr[i] != group_arr[start]:
            _fill_group_windows(values[start:i], out[start:i], sequence_length)
            start = i

    return out


def _fill_group_windows(group_values: np.ndarray, out_slice: np.ndarray, sequence_length: int) -> None:
    n = len(group_values)
    for j in range(n):
        window_start = j - sequence_length + 1
        if window_start < 0:
            pad_len = -window_start
            out_slice[j, pad_len:, :] = group_values[0 : j + 1]
        else:
            out_slice[j, :, :] = group_values[window_start : j + 1]


class SequenceDataset(Dataset):
    """Plain torch Dataset over pre-built (N, seq_len, n_features) windows."""

    def __init__(self, sequences: np.ndarray, targets: Optional[np.ndarray] = None,
                 sample_weight: Optional[np.ndarray] = None):
        self.sequences = torch.as_tensor(sequences, dtype=torch.float32)
        self.targets = None if targets is None else torch.as_tensor(targets, dtype=torch.float32)
        self.sample_weight = None if sample_weight is None else torch.as_tensor(sample_weight, dtype=torch.float32)

    def __len__(self) -> int:
        return len(self.sequences)

    def __getitem__(self, idx: int):
        if self.targets is None:
            return self.sequences[idx]
        if self.sample_weight is None:
            return self.sequences[idx], self.targets[idx]
        return self.sequences[idx], self.targets[idx], self.sample_weight[idx]


class EarlyStopper:
    """Tracks the best validation loss seen so far; signals when to stop and
    whether the current epoch produced a new best (so callers can checkpoint
    the best state_dict in memory without needing disk I/O mid-training)."""

    def __init__(self, patience: int = 10, min_delta: float = 1e-5):
        self.patience = patience
        self.min_delta = min_delta
        self.best_loss = float("inf")
        self.counter = 0

    def step(self, val_loss: float) -> tuple:
        """Returns (should_stop: bool, is_best: bool)."""
        if val_loss < self.best_loss - self.min_delta:
            self.best_loss = val_loss
            self.counter = 0
            return False, True
        self.counter += 1
        return self.counter >= self.patience, False
