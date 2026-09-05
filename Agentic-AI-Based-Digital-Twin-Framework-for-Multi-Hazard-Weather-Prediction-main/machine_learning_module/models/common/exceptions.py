"""Custom exception hierarchy for the ML framework."""


class FrameworkError(Exception):
    """Base class for all framework-raised exceptions."""


class ConfigValidationError(FrameworkError):
    """Raised when a model configuration fails validation."""


class DataValidationError(FrameworkError):
    """Raised when input data does not match expected schema/shape."""


class ModelNotFittedError(FrameworkError):
    """Raised when predict/evaluate is called before fit()."""


class SerializationError(FrameworkError):
    """Raised when saving or loading a model artifact fails."""


class TrainingError(FrameworkError):
    """Raised when model training fails for a non-configuration reason."""


class TuningError(FrameworkError):
    """Raised when hyperparameter tuning fails or produces no valid trial."""
