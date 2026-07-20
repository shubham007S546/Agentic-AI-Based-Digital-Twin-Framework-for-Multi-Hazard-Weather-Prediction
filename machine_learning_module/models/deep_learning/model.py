"""
Deep-learning model wrapper: LSTM / GRU / TCN, task-aware (regression /
binary / multiclass), plugged into the same BaseModel contract used by
random_forest / xgboost / lightgbm so it's a drop-in fourth algorithm.

Design note
-----------
BaseModel.fit/predict already handle log1p target-transform, sample_weight,
and eval_set plumbing generically (see models/common/base_model.py) -- they
just forward everything to `self._estimator.fit(...)` /
`self._estimator.predict(...)`. So instead of overriding BaseModel.fit (like
LightGBMModel does, because lightgbm's native callback API needs it),
DeepLearningModel only implements `_build_estimator`, returning a
`TorchSequenceEstimator` that itself duck-types the sklearn-style
`.fit(X, y, sample_weight=None, eval_set=None, **kwargs)` /
`.predict(X)` / `.predict_proba(X)` interface. That keeps train.py /
evaluate.py / predict.py essentially identical in shape to lightgbm's.

Row alignment
-------------
X here is tabular (one row per timestamp/location, same shape as the other
algorithms' X_train.csv). To feed a sequence model we build a sliding window
ending at each row via `build_padded_sequences` (zero-padded at the start of
each group so every row still gets a prediction) -- this is what lets
predict(X) return exactly len(X) values, matching what BaseEvaluator expects.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np
import pandas as pd

try:
    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "The 'torch' package is required for deep_learning models. "
        "Install it with: pip install torch --index-url https://download.pytorch.org/whl/cpu"
    ) from exc

from models.common.base_model import BaseModel
from models.common.config_schema import TaskType
from models.common.logging_config import get_logger
from models.common.torch_utils import (
    EarlyStopper,
    SequenceDataset,
    build_padded_sequences,
    get_device,
    set_torch_seed,
)

from .config import DeepLearningConfig

logger = get_logger(__name__)


# --------------------------------------------------------------------------- #
# Architectures
# --------------------------------------------------------------------------- #
class LSTMNet(nn.Module):
    def __init__(self, input_size: int, hidden_size: int, num_layers: int, dropout: float, output_size: int):
        super().__init__()
        self.rnn = nn.LSTM(
            input_size, hidden_size, num_layers, batch_first=True,
            dropout=dropout if num_layers > 1 else 0.0,
        )
        self.head = nn.Sequential(
            nn.Linear(hidden_size, max(hidden_size // 2, 8)),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(max(hidden_size // 2, 8), output_size),
        )

    def forward(self, x: "torch.Tensor") -> "torch.Tensor":
        out, _ = self.rnn(x)
        return self.head(out[:, -1, :])


class GRUNet(nn.Module):
    def __init__(self, input_size: int, hidden_size: int, num_layers: int, dropout: float, output_size: int):
        super().__init__()
        self.rnn = nn.GRU(
            input_size, hidden_size, num_layers, batch_first=True,
            dropout=dropout if num_layers > 1 else 0.0,
        )
        self.head = nn.Sequential(
            nn.Linear(hidden_size, max(hidden_size // 2, 8)),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(max(hidden_size // 2, 8), output_size),
        )

    def forward(self, x: "torch.Tensor") -> "torch.Tensor":
        out, _ = self.rnn(x)
        return self.head(out[:, -1, :])


class _Chomp1d(nn.Module):
    """Trims the extra right-padding a causal dilated conv adds, so output
    length matches input length and no future timestep leaks in."""

    def __init__(self, chomp_size: int):
        super().__init__()
        self.chomp_size = chomp_size

    def forward(self, x: "torch.Tensor") -> "torch.Tensor":
        return x[:, :, :-self.chomp_size].contiguous() if self.chomp_size > 0 else x


class _TemporalBlock(nn.Module):
    def __init__(self, n_inputs: int, n_outputs: int, kernel_size: int, dilation: int, dropout: float):
        super().__init__()
        padding = (kernel_size - 1) * dilation
        self.net = nn.Sequential(
            nn.Conv1d(n_inputs, n_outputs, kernel_size, padding=padding, dilation=dilation),
            _Chomp1d(padding),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Conv1d(n_outputs, n_outputs, kernel_size, padding=padding, dilation=dilation),
            _Chomp1d(padding),
            nn.ReLU(),
            nn.Dropout(dropout),
        )
        self.downsample = nn.Conv1d(n_inputs, n_outputs, 1) if n_inputs != n_outputs else None
        self.relu = nn.ReLU()

    def forward(self, x: "torch.Tensor") -> "torch.Tensor":
        out = self.net(x)
        res = x if self.downsample is None else self.downsample(x)
        return self.relu(out + res)


class TCNNet(nn.Module):
    """Temporal Convolutional Network: stacked causal dilated conv blocks
    with residual connections, reading input as (batch, seq_len, features)
    like the RNNs above (transposed internally for Conv1d)."""

    def __init__(self, input_size: int, channels: list, kernel_size: int, dropout: float, output_size: int):
        super().__init__()
        layers = []
        for i, out_ch in enumerate(channels):
            in_ch = input_size if i == 0 else channels[i - 1]
            layers.append(_TemporalBlock(in_ch, out_ch, kernel_size, dilation=2 ** i, dropout=dropout))
        self.tcn = nn.Sequential(*layers)
        self.head = nn.Linear(channels[-1], output_size)

    def forward(self, x: "torch.Tensor") -> "torch.Tensor":
        x = x.transpose(1, 2)          # (batch, features, seq_len) for Conv1d
        y = self.tcn(x)
        return self.head(y[:, :, -1])  # last timestep


def _build_net(architecture: str, input_size: int, cfg: DeepLearningConfig, output_size: int) -> nn.Module:
    if architecture == "lstm":
        return LSTMNet(input_size, cfg.hidden_size, cfg.num_layers, cfg.dropout, output_size)
    if architecture == "gru":
        return GRUNet(input_size, cfg.hidden_size, cfg.num_layers, cfg.dropout, output_size)
    if architecture == "tcn":
        return TCNNet(input_size, cfg.tcn_channels, cfg.tcn_kernel_size, cfg.dropout, output_size)
    raise ValueError(f"Unknown architecture: {architecture!r}")


# --------------------------------------------------------------------------- #
# Estimator (duck-typed sklearn-style .fit/.predict/.predict_proba)
# --------------------------------------------------------------------------- #
class TorchSequenceEstimator:
    def __init__(self, config: DeepLearningConfig, architecture: Optional[str] = None):
        self.cfg = config
        self.architecture = architecture or config.architecture
        self.device_ = get_device(config.device)
        self.net: Optional[nn.Module] = None
        self.feature_columns_: Optional[list] = None
        self.history_: list = []
        self.is_fitted_ = False

    # -- data prep ---------------------------------------------------- #
    def _split_group(self, X: pd.DataFrame):
        gc = self.cfg.group_column
        if gc and gc in X.columns:
            return X.drop(columns=[gc]), X[gc]
        return X, None

    def _to_sequences(self, X: pd.DataFrame) -> np.ndarray:
        numeric_X, group_ids = self._split_group(X)
        if self.feature_columns_ is None:
            self.feature_columns_ = list(numeric_X.columns)
        numeric_X = numeric_X[self.feature_columns_]
        return build_padded_sequences(numeric_X, self.cfg.sequence_length, group_ids)

    # -- loss ------------------------------------------------------------ #
    def _output_size(self) -> int:
        if self.cfg.task_type == TaskType.MULTICLASS_CLASSIFICATION:
            return self.cfg.num_classes
        return 1

    def _make_criterion(self, class_weights: Optional[dict]):
        tt = self.cfg.task_type
        if tt == TaskType.REGRESSION:
            return nn.MSELoss(reduction="none")
        if tt == TaskType.BINARY_CLASSIFICATION:
            pos_weight = None
            if class_weights:
                w0, w1 = class_weights.get(0, 1.0), class_weights.get(1, 1.0)
                pos_weight = torch.tensor([w1 / w0 if w0 else 1.0], device=self.device_)
            return nn.BCEWithLogitsLoss(pos_weight=pos_weight, reduction="none")
        weight = None
        if class_weights:
            weight = torch.tensor(
                [class_weights.get(i, 1.0) for i in range(self.cfg.num_classes)],
                dtype=torch.float32, device=self.device_,
            )
        return nn.CrossEntropyLoss(weight=weight, reduction="none")

    def _loss(self, criterion, logits: "torch.Tensor", yb: "torch.Tensor", wb: Optional["torch.Tensor"]):
        tt = self.cfg.task_type
        if tt == TaskType.MULTICLASS_CLASSIFICATION:
            per_sample = criterion(logits, yb.long())
        else:
            per_sample = criterion(logits.squeeze(-1), yb)
        if wb is not None:
            return (per_sample * wb).sum() / wb.sum().clamp_min(1e-8)
        return per_sample.mean()

    # -- fit / eval loop --------------------------------------------- #
    def fit(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        sample_weight: Optional[np.ndarray] = None,
        eval_set: Optional[list] = None,
        class_weights: Optional[dict] = None,
        **kwargs: Any,
    ) -> "TorchSequenceEstimator":
        set_torch_seed(self.cfg.random_seed)
        cfg = self.cfg

        seqs = self._to_sequences(X)
        y_arr = y.to_numpy(dtype=np.float32)
        self.net = _build_net(self.architecture, seqs.shape[-1], cfg, self._output_size()).to(self.device_)

        train_loader = DataLoader(
            SequenceDataset(seqs, y_arr, sample_weight), batch_size=cfg.batch_size, shuffle=True
        )

        val_loader = None
        if eval_set:
            X_val, y_val = eval_set[0]
            val_seqs = self._to_sequences(X_val)
            val_loader = DataLoader(
                SequenceDataset(val_seqs, y_val.to_numpy(dtype=np.float32)),
                batch_size=cfg.batch_size, shuffle=False,
            )

        optimizer = torch.optim.Adam(self.net.parameters(), lr=cfg.learning_rate, weight_decay=cfg.weight_decay)
        criterion = self._make_criterion(class_weights)
        stopper = EarlyStopper(patience=cfg.early_stopping_patience)
        best_state = None
        self.history_ = []

        for epoch in range(cfg.epochs):
            self.net.train()
            running, n_seen = 0.0, 0
            for batch in train_loader:
                if len(batch) == 3:
                    xb, yb, wb = batch
                    wb = wb.to(self.device_)
                else:
                    xb, yb = batch
                    wb = None
                xb, yb = xb.to(self.device_), yb.to(self.device_)

                optimizer.zero_grad()
                logits = self.net(xb)
                loss = self._loss(criterion, logits, yb, wb)
                loss.backward()
                if cfg.grad_clip_norm:
                    nn.utils.clip_grad_norm_(self.net.parameters(), cfg.grad_clip_norm)
                optimizer.step()

                running += loss.item() * xb.size(0)
                n_seen += xb.size(0)
            train_loss = running / max(n_seen, 1)

            if val_loader is not None:
                val_loss = self._eval_loss(criterion, val_loader)
                self.history_.append({"epoch": epoch, "train_loss": train_loss, "val_loss": val_loss})
                should_stop, is_best = stopper.step(val_loss)
                if is_best:
                    best_state = {k: v.detach().clone() for k, v in self.net.state_dict().items()}
                if should_stop:
                    logger.info("Early stopping at epoch %d (best val_loss=%.5f)", epoch, stopper.best_loss)
                    break
            else:
                self.history_.append({"epoch": epoch, "train_loss": train_loss})

        if best_state is not None:
            self.net.load_state_dict(best_state)

        self.is_fitted_ = True
        return self

    def _eval_loss(self, criterion, loader) -> float:
        self.net.eval()
        total, n = 0.0, 0
        with torch.no_grad():
            for xb, yb in loader:
                xb, yb = xb.to(self.device_), yb.to(self.device_)
                logits = self.net(xb)
                loss = self._loss(criterion, logits, yb, None)
                total += loss.item() * xb.size(0)
                n += xb.size(0)
        return total / max(n, 1)

    # -- inference ------------------------------------------------------- #
    def predict(self, X: pd.DataFrame) -> np.ndarray:
        self.net.eval()
        seqs = self._to_sequences(X)
        loader = DataLoader(SequenceDataset(seqs), batch_size=self.cfg.batch_size, shuffle=False)
        outputs = []
        with torch.no_grad():
            for xb in loader:
                xb = xb.to(self.device_)
                logits = self.net(xb)
                if self.cfg.task_type == TaskType.REGRESSION:
                    outputs.append(logits.squeeze(-1).cpu().numpy())
                elif self.cfg.task_type == TaskType.BINARY_CLASSIFICATION:
                    probs = torch.sigmoid(logits.squeeze(-1))
                    outputs.append((probs >= 0.5).long().cpu().numpy())
                else:
                    outputs.append(torch.argmax(logits, dim=1).cpu().numpy())
        return np.concatenate(outputs)

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        self.net.eval()
        seqs = self._to_sequences(X)
        loader = DataLoader(SequenceDataset(seqs), batch_size=self.cfg.batch_size, shuffle=False)
        outputs = []
        with torch.no_grad():
            for xb in loader:
                xb = xb.to(self.device_)
                logits = self.net(xb)
                if self.cfg.task_type == TaskType.BINARY_CLASSIFICATION:
                    p1 = torch.sigmoid(logits.squeeze(-1))
                    p = torch.stack([1 - p1, p1], dim=1)
                else:
                    p = torch.softmax(logits, dim=1)
                outputs.append(p.cpu().numpy())
        return np.concatenate(outputs, axis=0)


# --------------------------------------------------------------------------- #
# BaseModel adapter
# --------------------------------------------------------------------------- #
class DeepLearningModel(BaseModel):
    """LSTM / GRU / TCN behind the standard BaseModel contract. Relies on
    BaseModel.fit/predict (unmodified) for log1p transform + sample_weight +
    eval_set plumbing; only `_build_estimator` is implemented here."""

    def __init__(self, config: DeepLearningConfig):
        super().__init__(config)
        self.config: DeepLearningConfig = config

    def _build_estimator(self, params: Optional[dict] = None) -> Any:
        cfg = self.config
        if params:
            # shallow-copy config with tuner overrides for this trial, without
            # mutating self.config (mirrors how lightgbm/xgboost handle `params`)
            from dataclasses import replace
            cfg = replace(cfg, **{k: v for k, v in params.items() if hasattr(cfg, k)})
        return TorchSequenceEstimator(cfg)

    def get_training_history(self) -> list:
        self._check_fitted()
        return self._estimator.history_
