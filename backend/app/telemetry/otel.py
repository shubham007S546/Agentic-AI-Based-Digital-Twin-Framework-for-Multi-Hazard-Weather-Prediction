"""
app/telemetry/otel.py
─────────────────────
OpenTelemetry distributed tracing and metrics setup.

Design decisions:
  • OTLP gRPC exporter is used because it's the standard for Jaeger, Tempo,
    and the OpenTelemetry Collector — all interoperable.
  • Auto-instrumentation for FastAPI, SQLAlchemy, Redis, and httpx means
    every database query and external HTTP call is traced without code changes.
  • W3C Trace Context headers (traceparent) are propagated, so traces from
    the Next.js frontend can be correlated with backend traces.
  • The tracer and meter are module-level singletons initialized at startup,
    accessed via get_tracer() / get_meter() factories — not global state.
  • When OTEL is disabled (e.g., test environment), the NoOp implementations
    are used — zero overhead, zero configuration required.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import (
    DEPLOYMENT_ENVIRONMENT,
    SERVICE_NAME,
    SERVICE_VERSION,
    Resource,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

import structlog

logger = structlog.get_logger(__name__)

# ── Module-level providers (initialized once at startup) ──────────────────────
_tracer_provider: Optional[TracerProvider] = None
_meter_provider: Optional[MeterProvider] = None


def setup_telemetry(
    *,
    service_name: str,
    service_version: str,
    environment: str,
    otlp_endpoint: str,
    enabled: bool = True,
) -> None:
    """
    Initialize OpenTelemetry SDK — call once at application startup.

    Args:
        service_name:    Identifies this service in Jaeger/Tempo dashboards.
        service_version: Semantic version (for version-based trace filtering).
        environment:     deployment environment (development|staging|production).
        otlp_endpoint:   gRPC endpoint for the OTLP collector (e.g., http://localhost:4317).
        enabled:         When False, installs NoOp providers (for tests).
    """
    global _tracer_provider, _meter_provider

    resource = Resource.create(
        {
            SERVICE_NAME: service_name,
            SERVICE_VERSION: service_version,
            DEPLOYMENT_ENVIRONMENT: environment,
        }
    )

    if not enabled:
        # NoOp providers — zero overhead in test environments
        trace.set_tracer_provider(trace.NoOpTracerProvider())
        _tracer_provider = None
        logger.info("OpenTelemetry disabled — NoOp providers installed")
        return

    # ── Tracing ───────────────────────────────────────────────────────────────
    tracer_provider = TracerProvider(resource=resource)

    try:
        otlp_span_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
        tracer_provider.add_span_processor(BatchSpanProcessor(otlp_span_exporter))
    except Exception as exc:
        # Fallback to console exporter if OTLP collector is unreachable
        logger.warning(
            "OTLP span exporter unavailable — falling back to console",
            error=str(exc),
            endpoint=otlp_endpoint,
        )
        tracer_provider.add_span_processor(
            BatchSpanProcessor(ConsoleSpanExporter())
        )

    trace.set_tracer_provider(tracer_provider)
    _tracer_provider = tracer_provider

    # ── Metrics ───────────────────────────────────────────────────────────────
    try:
        otlp_metric_exporter = OTLPMetricExporter(endpoint=otlp_endpoint, insecure=True)
        metric_reader = PeriodicExportingMetricReader(otlp_metric_exporter, export_interval_millis=60_000)
        meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
        metrics.set_meter_provider(meter_provider)
        _meter_provider = meter_provider
    except Exception as exc:
        logger.warning("OTLP metric exporter unavailable", error=str(exc))

    # ── W3C Trace Context propagation ─────────────────────────────────────────
    # This ensures the traceparent header from Next.js is respected and that
    # spans created here are correctly parented.
    from opentelemetry import propagate
    from opentelemetry.propagators.composite import CompositePropagator
    from opentelemetry.baggage.propagation import W3CBaggagePropagator

    propagate.set_global_textmap(
        CompositePropagator([TraceContextTextMapPropagator(), W3CBaggagePropagator()])
    )

    logger.info(
        "OpenTelemetry initialized",
        service=service_name,
        version=service_version,
        otlp_endpoint=otlp_endpoint,
    )


def instrument_fastapi(app: object) -> None:
    """
    Auto-instrument a FastAPI application.

    Must be called AFTER setup_telemetry() and AFTER the FastAPI app is created,
    but BEFORE the app starts handling requests.
    """
    FastAPIInstrumentor.instrument_app(app)  # type: ignore[arg-type]
    logger.info("FastAPI instrumented with OpenTelemetry")


def instrument_sqlalchemy(engine: object) -> None:
    """Auto-instrument SQLAlchemy to create spans for every query."""
    SQLAlchemyInstrumentor().instrument(engine=engine)  # type: ignore[call-arg]
    logger.info("SQLAlchemy instrumented with OpenTelemetry")


def instrument_redis() -> None:
    """Auto-instrument Redis client for all cache operations."""
    RedisInstrumentor().instrument()
    logger.info("Redis instrumented with OpenTelemetry")


def instrument_httpx() -> None:
    """Auto-instrument all httpx HTTP client calls (weather APIs, etc.)."""
    HTTPXClientInstrumentor().instrument()
    logger.info("HTTPX instrumented with OpenTelemetry")


@lru_cache(maxsize=32)
def get_tracer(name: str) -> trace.Tracer:
    """
    Get a named tracer for creating custom spans.

    Usage:
        from app.telemetry.otel import get_tracer
        tracer = get_tracer(__name__)

        async def run_prediction():
            with tracer.start_as_current_span("ml.inference") as span:
                span.set_attribute("model.name", "xgboost_rainfall_v1")
                result = model.predict(features)
                span.set_attribute("prediction.value", result)
    """
    return trace.get_tracer(name)


def get_current_trace_id() -> str:
    """Extract the current trace ID as a hex string for log correlation."""
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if ctx and ctx.is_valid:
        return format(ctx.trace_id, "032x")
    return ""


def get_current_span_id() -> str:
    """Extract the current span ID as a hex string for log correlation."""
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if ctx and ctx.is_valid:
        return format(ctx.span_id, "016x")
    return ""


def shutdown_telemetry() -> None:
    """
    Flush and shut down telemetry providers.
    Called during application shutdown to ensure all pending spans are exported.
    """
    global _tracer_provider, _meter_provider
    if _tracer_provider:
        _tracer_provider.shutdown()
        logger.info("TracerProvider shut down")
    if _meter_provider:
        _meter_provider.shutdown()
        logger.info("MeterProvider shut down")
