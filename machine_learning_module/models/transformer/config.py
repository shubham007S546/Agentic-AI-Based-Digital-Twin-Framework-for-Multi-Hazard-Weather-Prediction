"""Configuration for the transformer package (TFT-Lite: a compact Temporal
Fusion Transformer -- variable selection network + LSTM encoder + causal
self-attention, following Lim et al. 2019 but simplified: no separate
static/known-future covariate handling, single-horizon output)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from models.common.config_schema import BaseModelConfig
from models.common.exceptions import ConfigValidationError


@dataclass
class TFTLiteConfig(BaseModelConfig):
    """TFT-Lite specific hyperparameters, on top of the shared fields in
    BaseModelConfig."""

    model_name: str = "transformer"

    # sequence windowing (same semantics as deep_learning's DeepLearningConfig)
    sequence_length: int = 24
    group_column: Optional[str] = None

    # architecture
    hidden_size: int = 64
    num_attention_heads: int = 4
    num_lstm_layers: int = 1
    dropout: float = 0.1

    num_classes: int = 2  # only used when task_type is classification

    # optimization
    batch_size: int = 64
    epochs: int = 100
    learning_rate: float = 1e-3
    weight_decay: float = 1e-5
    early_stopping_patience: int = 10
    grad_clip_norm: Optional[float] = 1.0

    device: str = "cpu"  # "cpu" | "cuda" | "auto"

    def validate(self) -> None:
        super().validate()

        if self.sequence_length <= 0:
            raise ConfigValidationError("sequence_length must be > 0.")
        if self.hidden_size <= 0:
            raise ConfigValidationError("hidden_size must be > 0.")
        if self.num_attention_heads <= 0:
            raise ConfigValidationError("num_attention_heads must be > 0.")
        if self.hidden_size % self.num_attention_heads != 0:
            raise ConfigValidationError(
                f"hidden_size ({self.hidden_size}) must be divisible by "
                f"num_attention_heads ({self.num_attention_heads})."
            )
        if self.num_lstm_layers <= 0:
            raise ConfigValidationError("num_lstm_layers must be > 0.")
        if not (0.0 <= self.dropout < 1.0):
            raise ConfigValidationError("dropout must be in [0, 1).")
        if self.num_classes < 2:
            raise ConfigValidationError("num_classes must be >= 2.")
        if self.batch_size <= 0:
            raise ConfigValidationError("batch_size must be > 0.")
        if self.epochs <= 0:
            raise ConfigValidationError("epochs must be > 0.")
        if self.learning_rate <= 0:
            raise ConfigValidationError("learning_rate must be > 0.")
        if self.early_stopping_patience <= 0:
            raise ConfigValidationError("early_stopping_patience must be > 0.")
        if self.device not in ("cpu", "cuda", "auto"):
            raise ConfigValidationError("device must be one of: cpu, cuda, auto.")
