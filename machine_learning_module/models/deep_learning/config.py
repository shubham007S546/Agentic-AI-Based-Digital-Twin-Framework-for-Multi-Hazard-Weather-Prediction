"""Configuration for the deep_learning package (LSTM / GRU / TCN)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from models.common.config_schema import BaseModelConfig
from models.common.exceptions import ConfigValidationError

_VALID_ARCHITECTURES = ("lstm", "gru", "tcn")


@dataclass
class DeepLearningConfig(BaseModelConfig):
    """
    Deep-learning specific hyperparameters, on top of the shared fields in
    BaseModelConfig. One config drives all three architectures; unused
    fields for a given architecture (e.g. tcn_channels when architecture
    is "lstm") are simply ignored.
    """

    model_name: str = "deep_learning"

    architecture: str = "lstm"          # "lstm" | "gru" | "tcn"

    # sequence windowing
    sequence_length: int = 24           # rows of history per prediction window
    group_column: Optional[str] = None  # e.g. "district_id"; keeps windows from
                                         # bleeding across unrelated series. Must
                                         # be a real column present in X.

    # LSTM/GRU
    hidden_size: int = 64
    num_layers: int = 2
    dropout: float = 0.2

    # TCN
    tcn_channels: List[int] = field(default_factory=lambda: [64, 64, 64])
    tcn_kernel_size: int = 3

    # classification
    num_classes: int = 2                # only used when task_type is classification

    # optimization
    batch_size: int = 64
    epochs: int = 100
    learning_rate: float = 1e-3
    weight_decay: float = 1e-5
    early_stopping_patience: int = 10
    grad_clip_norm: Optional[float] = 1.0

    device: str = "cpu"                 # "cpu" | "cuda" | "auto"

    def validate(self) -> None:
        super().validate()

        if self.architecture not in _VALID_ARCHITECTURES:
            raise ConfigValidationError(
                f"architecture must be one of {_VALID_ARCHITECTURES}, got {self.architecture!r}."
            )
        if self.sequence_length <= 0:
            raise ConfigValidationError("sequence_length must be > 0.")
        if self.hidden_size <= 0:
            raise ConfigValidationError("hidden_size must be > 0.")
        if self.num_layers <= 0:
            raise ConfigValidationError("num_layers must be > 0.")
        if not (0.0 <= self.dropout < 1.0):
            raise ConfigValidationError("dropout must be in [0, 1).")
        if not self.tcn_channels or any(c <= 0 for c in self.tcn_channels):
            raise ConfigValidationError("tcn_channels must be a non-empty list of positive ints.")
        if self.tcn_kernel_size <= 1:
            raise ConfigValidationError("tcn_kernel_size must be > 1.")
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
