"""
app/logging/structured_logger.py
─────────────────────────────────
Structured JSON logging using structlog.

Design decisions:
  • structlog is chosen over plain logging because it produces machine-parseable
    JSON by default, is async-safe (uses immutable contexts), and integrates
    naturally with OpenTelemetry trace/span IDs.
  • contextvars-based context binding means each request's log records
    automatically include request_id, user_id, trace_id without manual threading.
  • In development, output is colorized/pretty-printed for readability.
  • In production (APP_ENV=production), output is newline-delimited JSON for
    log aggregators (Loki, CloudWatch, Datadog).
  • stdlib logging is re-routed through structlog so third-party libraries
    (SQLAlchemy, httpx, etc.) also produce structured output.
"""

from __future__ import annotations

import logging
import sys
from contextvars import ContextVar
from typing import Any

import structlog
from structlog.types import EventDict, WrappedLogger

# ── Context variables injected by middleware ──────────────────────────────────
# These are set per-request and automatically included in every log record
# produced during that request's lifecycle.

_request_id_var: ContextVar[str] = ContextVar("request_id", default="")
_user_id_var: ContextVar[str] = ContextVar("user_id", default="")
_trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")
_span_id_var: ContextVar[str] = ContextVar("span_id", default="")


def set_log_context(
    *,
    request_id: str = "",
    user_id: str = "",
    trace_id: str = "",
    span_id: str = "",
) -> None:
    """Called by middleware to inject per-request context into all log records."""
    _request_id_var.set(request_id)
    _user_id_var.set(user_id)
    _trace_id_var.set(trace_id)
    _span_id_var.set(span_id)


def clear_log_context() -> None:
    """Called after request completes to reset context variables."""
    _request_id_var.set("")
    _user_id_var.set("")
    _trace_id_var.set("")
    _span_id_var.set("")


# ── Custom processors ─────────────────────────────────────────────────────────

def _inject_request_context(
    logger: WrappedLogger,
    method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """
    Processor that injects request context variables into every log event.
    Because structlog processors are called in order, this runs early in the chain.
    """
    if request_id := _request_id_var.get():
        event_dict["request_id"] = request_id
    if user_id := _user_id_var.get():
        event_dict["user_id"] = user_id
    if trace_id := _trace_id_var.get():
        event_dict["trace_id"] = trace_id
    if span_id := _span_id_var.get():
        event_dict["span_id"] = span_id
    return event_dict


def _add_log_level_name(
    logger: WrappedLogger,
    method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """Normalize log level to uppercase string."""
    event_dict["level"] = method_name.upper()
    return event_dict


def _drop_color_message_key(
    logger: WrappedLogger,
    method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """Remove Uvicorn's color_message key that would pollute JSON output."""
    event_dict.pop("color_message", None)
    return event_dict


# ── Setup function ────────────────────────────────────────────────────────────

def setup_logging(*, level: str = "INFO", use_json: bool = True) -> None:
    """
    Configure structlog and stdlib logging.

    Args:
        level:    Log level string (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        use_json: If True, output newline-delimited JSON (production).
                  If False, pretty-print with colors (development).

    Must be called ONCE at application startup, before any loggers are created.
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Shared processors used by both structlog and stdlib
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        _inject_request_context,
        _add_log_level_name,
        _drop_color_message_key,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if use_json:
        # Production: clean JSON, one record per line
        renderer: Any = structlog.processors.JSONRenderer()
    else:
        # Development: human-readable colored output
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        cache_logger_on_first_use=True,
    )

    # Configure stdlib logging to route through structlog's formatter
    formatter = structlog.stdlib.ProcessorFormatter(
        # Processors applied only to stdlib log records
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    # Root logger — catches everything
    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(log_level)

    # Silence noisy third-party loggers at a higher level
    _LIBRARY_LOG_LEVELS: dict[str, int] = {
        "uvicorn": logging.INFO,
        "uvicorn.error": logging.INFO,
        "uvicorn.access": logging.WARNING,  # access logs come from our middleware
        "sqlalchemy.engine": logging.WARNING,
        "sqlalchemy.pool": logging.WARNING,
        "httpx": logging.WARNING,
        "httpcore": logging.WARNING,
        "celery": logging.INFO,
        "kombu": logging.WARNING,
        "boto3": logging.WARNING,
        "botocore": logging.WARNING,
        "opentelemetry": logging.WARNING,
    }
    for lib_name, lib_level in _LIBRARY_LOG_LEVELS.items():
        logging.getLogger(lib_name).setLevel(lib_level)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """
    Factory function for getting a named structlog logger.

    Usage:
        from app.logging.structured_logger import get_logger
        logger = get_logger(__name__)
        logger.info("Prediction complete", model="xgboost", latency_ms=42)
    """
    return structlog.get_logger(name)
