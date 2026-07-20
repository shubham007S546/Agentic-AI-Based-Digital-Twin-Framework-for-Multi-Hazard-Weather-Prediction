"""
TFT-Lite: a compact Temporal Fusion Transformer, task-aware (regression /
binary / multiclass), plugged into the same BaseModel contract as every
other algorithm in this framework.

Architecture (simplified from Lim et al. 2019, "Temporal Fusion
Transformers for Interpretable Multi-horizon Time Series Forecasting"):

    input (batch, seq_len, n_features)
      -> Variable Selection Network   (learns a per-timestep softmax weight
                                        over features via per-feature GRNs,
                                        so the model can down-weight noisy
                                        inputs like the flat-fill artifacts
                                        common in this project's rainfall data)
      -> LSTM encoder                 (local sequential processing)
      -> gated skip-connection + LayerNorm
      -> causal multi-head self-attention (longer-range temporal patterns)
      -> gated skip-connection + LayerNorm
      -> output Gated Residual Network -> Linear head on the last timestep

Simplifications versus the full paper: single-horizon output (not
multi-step forecasting), no separate static/known-future covariate
branches (there's no such split in the current tabular dataset), no
quantile outputs. These can be added later without touching the rest of
the framework, since -- like deep_learning -- this only replaces
`_build_estimator`; BaseModel.fit/predict handle target-transform and
sample_weight generically.
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
        "The 'torch' package is required for transformer models. "
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

from .config import TFTLiteConfig

logger = get_logger(__name__)


# --------------------------------------------------------------------------- #
# Building blocks
# --------------------------------------------------------------------------- #
class GatedLinearUnit(nn.Module):
    """GLU(x) = sigmoid(W_gate x) * (W_value x) -- lets the network learn to
    suppress a branch entirely (gate -> 0) rather than being forced to use it,
    which is what makes GRN skip-connections safe to stack deeply."""

    def __init__(self, input_size: int, output_size: Optional[int] = None):
        super().__init__()
        output_size = output_size or input_size
        self.fc = nn.Linear(input_size, output_size * 2)

    def forward(self, x: "torch.Tensor") -> "torch.Tensor":
        value, gate = self.fc(x).chunk(2, dim=-1)
        return value * torch.sigmoid(gate)


class GatedResidualNetwork(nn.Module):
    """The core TFT building block: a 2-layer MLP with an optional extra
    context input, a GLU gate, and a residual + LayerNorm wrapper."""

    def __init__(self, input_size: int, hidden_size: int, output_size: Optional[int] = None,
                 dropout: float = 0.1, context_size: Optional[int] = None):
        super().__init__()
        output_size = output_size or input_size
        self.fc1 = nn.Linear(input_size, hidden_size)
        self.context_fc = nn.Linear(context_size, hidden_size, bias=False) if context_size else None
        self.elu = nn.ELU()
        self.fc2 = nn.Linear(hidden_size, output_size)
        self.dropout = nn.Dropout(dropout)
        self.gate = GatedLinearUnit(output_size, output_size)
        self.layer_norm = nn.LayerNorm(output_size)
        self.skip = nn.Linear(input_size, output_size) if input_size != output_size else None

    def forward(self, x: "torch.Tensor", context: Optional["torch.Tensor"] = None) -> "torch.Tensor":
        residual = x if self.skip is None else self.skip(x)
        h = self.fc1(x)
        if context is not None and self.context_fc is not None:
            h = h + self.context_fc(context)
        h = self.fc2(self.elu(h))
        h = self.gate(self.dropout(h))
        return self.layer_norm(h + residual)


class VariableSelectionNetwork(nn.Module):
    """Learns a per-timestep softmax weighting over input features: each
    scalar feature is first passed through its own small GRN, then a
    "flattened" GRN over all of them produces the selection weights."""

    def __init__(self, n_features: int, hidden_size: int, dropout: float = 0.1):
        super().__init__()
        self.n_features = n_features
        self.single_grns = nn.ModuleList([
            GatedResidualNetwork(1, hidden_size, hidden_size, dropout) for _ in range(n_features)
        ])
        self.flattened_grn = GatedResidualNetwork(n_features * hidden_size, hidden_size, n_features, dropout)

    def forward(self, x: "torch.Tensor"):
        # x: (batch, seq_len, n_features)
        processed = [self.single_grns[i](x[..., i:i + 1]) for i in range(self.n_features)]
        stacked = torch.stack(processed, dim=-2)        # (batch, seq_len, n_features, hidden)
        flattened = torch.cat(processed, dim=-1)         # (batch, seq_len, n_features*hidden)
        weights = torch.softmax(self.flattened_grn(flattened), dim=-1).unsqueeze(-1)
        combined = (stacked * weights).sum(dim=-2)        # (batch, seq_len, hidden)
        return combined, weights.squeeze(-1)               # combined, (batch, seq_len, n_features)


class TFTLiteNet(nn.Module):
    def __init__(self, input_size: int, hidden_size: int, num_heads: int,
                 num_lstm_layers: int, dropout: float, output_size: int):
        super().__init__()
        self.vsn = VariableSelectionNetwork(input_size, hidden_size, dropout)
        self.lstm = nn.LSTM(
            hidden_size, hidden_size, num_lstm_layers, batch_first=True,
            dropout=dropout if num_lstm_layers > 1 else 0.0,
        )
        self.post_lstm_gate = GatedLinearUnit(hidden_size, hidden_size)
        self.post_lstm_norm = nn.LayerNorm(hidden_size)

        self.attention = nn.MultiheadAttention(hidden_size, num_heads, dropout=dropout, batch_first=True)
        self.post_attn_gate = GatedLinearUnit(hidden_size, hidden_size)
        self.post_attn_norm = nn.LayerNorm(hidden_size)

        self.output_grn = GatedResidualNetwork(hidden_size, hidden_size, hidden_size, dropout)
        self.head = nn.Linear(hidden_size, output_size)

    def forward(self, x: "torch.Tensor") -> "torch.Tensor":
        seq_len = x.size(1)
        vsn_out, _ = self.vsn(x)

        lstm_out, _ = self.lstm(vsn_out)
        enriched = self.post_lstm_norm(self.post_lstm_gate(lstm_out) + vsn_out)

        causal_mask = torch.triu(
            torch.full((seq_len, seq_len), float("-inf"), device=x.device), diagonal=1
        )
        attn_out, _ = self.attention(enriched, enriched, enriched, attn_mask=causal_mask)
        attn_enriched = self.post_attn_norm(self.post_attn_gate(attn_out) + enriched)

        out = self.output_grn(attn_enriched)
        return self.head(out[:, -1, :])  # prediction from the last timestep


# --------------------------------------------------------------------------- #
# Estimator (duck-typed sklearn-style .fit/.predict/.predict_proba)
# --------------------------------------------------------------------------- #
class TFTEstimator:
    def __init__(self, config: TFTLiteConfig):
        self.cfg = config
        self.device_ = get_device(config.device)
        self.net: Optional[nn.Module] = None
        self.feature_columns_: Optional[list] = None
        self.history_: list = []
        self.is_fitted_ = False

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

    def _output_size(self) -> int:
        return self.cfg.num_classes if self.cfg.task_type == TaskType.MULTICLASS_CLASSIFICATION else 1

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

    def _loss(self, criterion, logits, yb, wb):
        if self.cfg.task_type == TaskType.MULTICLASS_CLASSIFICATION:
            per_sample = criterion(logits, yb.long())
        else:
            per_sample = criterion(logits.squeeze(-1), yb)
        if wb is not None:
            return (per_sample * wb).sum() / wb.sum().clamp_min(1e-8)
        return per_sample.mean()

    def fit(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        sample_weight: Optional[np.ndarray] = None,
        eval_set: Optional[list] = None,
        class_weights: Optional[dict] = None,
        **kwargs: Any,
    ) -> "TFTEstimator":
        set_torch_seed(self.cfg.random_seed)
        cfg = self.cfg

        seqs = self._to_sequences(X)
        y_arr = y.to_numpy(dtype=np.float32)
        self.net = TFTLiteNet(
            input_size=seqs.shape[-1], hidden_size=cfg.hidden_size, num_heads=cfg.num_attention_heads,
            num_lstm_layers=cfg.num_lstm_layers, dropout=cfg.dropout, output_size=self._output_size(),
        ).to(self.device_)

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

    def attention_weights(self, X: pd.DataFrame) -> np.ndarray:
        """Return the raw attention map (batch, heads, seq_len, seq_len) for
        the given input -- useful for interpreting which past timesteps the
        model leaned on most, a signature TFT feature."""
        self.net.eval()
        seqs = self._to_sequences(X)
        xb = torch.as_tensor(seqs, dtype=torch.float32, device=self.device_)
        with torch.no_grad():
            vsn_out, _ = self.net.vsn(xb)
            lstm_out, _ = self.net.lstm(vsn_out)
            enriched = self.net.post_lstm_norm(self.net.post_lstm_gate(lstm_out) + vsn_out)
            seq_len = xb.size(1)
            causal_mask = torch.triu(torch.full((seq_len, seq_len), float("-inf"), device=xb.device), diagonal=1)
            _, attn_weights = self.net.attention(
                enriched, enriched, enriched, attn_mask=causal_mask, average_attn_weights=False
            )
        return attn_weights.cpu().numpy()


# --------------------------------------------------------------------------- #
# BaseModel adapter
# --------------------------------------------------------------------------- #
class TFTLiteModel(BaseModel):
    """TFT-Lite behind the standard BaseModel contract. Relies on BaseModel.
    fit/predict (unmodified) for log1p transform + sample_weight + eval_set
    plumbing; only `_build_estimator` is implemented here."""

    def __init__(self, config: TFTLiteConfig):
        super().__init__(config)
        self.config: TFTLiteConfig = config

    def _build_estimator(self, params: Optional[dict] = None) -> Any:
        cfg = self.config
        if params:
            from dataclasses import replace
            cfg = replace(cfg, **{k: v for k, v in params.items() if hasattr(cfg, k)})
        return TFTEstimator(cfg)

    def get_training_history(self) -> list:
        self._check_fitted()
        return self._estimator.history_

    def get_attention_weights(self, X: pd.DataFrame) -> np.ndarray:
        self._check_fitted()
        return self._estimator.attention_weights(X)
