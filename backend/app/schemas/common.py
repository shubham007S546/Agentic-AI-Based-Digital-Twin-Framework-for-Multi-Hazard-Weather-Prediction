"""
app/schemas/common.py
──────────────────────
Shared Pydantic v2 schemas used across all API endpoints.

Design decisions:
  • All API responses are wrapped in a typed envelope (ApiResponse[T]).
    This consistency means the Next.js frontend can handle ALL responses
    with a single axios interceptor — no per-endpoint response parsing.
  • Pagination follows the RFC 5988 pattern with page/page_size (not cursor)
    because the frontend uses DataTable-style pagination with page numbers.
  • ErrorResponse mirrors the exception handler's output format exactly so
    OpenAPI schema generation is accurate.
  • HealthStatus provides a hierarchical dependency health check format that
    Kubernetes, Grafana, and Prometheus all understand.
  • All models use model_config = ConfigDict(from_attributes=True) so they
    can be constructed from SQLAlchemy ORM objects without .model_dump() intermediate steps.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field

DataT = TypeVar("DataT")


# ══════════════════════════════════════════════════════════════════════════════
#  Response Envelope
# ══════════════════════════════════════════════════════════════════════════════

class ApiResponse(BaseModel, Generic[DataT]):
    """
    Standard API response wrapper for ALL successful responses.

    Usage:
        return ApiResponse(data=weather_data, message="Current weather retrieved")

    The frontend can reliably access response.data without type guessing.
    """

    success: bool = True
    data: DataT
    message: str = "OK"
    request_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(from_attributes=True)


class ApiListResponse(BaseModel, Generic[DataT]):
    """
    Standard API response for paginated list endpoints.

    Includes metadata for the frontend to render pagination controls.
    """

    success: bool = True
    data: list[DataT]
    message: str = "OK"
    pagination: "PaginationMeta"
    request_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(from_attributes=True)


class EmptyResponse(BaseModel):
    """Response for operations that return no content (e.g., DELETE)."""

    success: bool = True
    message: str = "Operation completed successfully."
    request_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ══════════════════════════════════════════════════════════════════════════════
#  Pagination
# ══════════════════════════════════════════════════════════════════════════════

class PaginationParams(BaseModel):
    """Query parameters for paginated endpoints."""

    page: int = Field(1, ge=1, description="Page number (1-indexed)")
    page_size: int = Field(20, ge=1, le=100, description="Items per page (max 100)")

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size


class PaginationMeta(BaseModel):
    """Pagination metadata included in list responses."""

    page: int = Field(description="Current page number")
    page_size: int = Field(description="Items per page")
    total_items: int = Field(description="Total items across all pages")
    total_pages: int = Field(description="Total number of pages")
    has_next: bool = Field(description="Whether a next page exists")
    has_previous: bool = Field(description="Whether a previous page exists")

    @classmethod
    def create(cls, *, page: int, page_size: int, total_items: int) -> "PaginationMeta":
        total_pages = max(1, -(-total_items // page_size))  # ceiling division
        return cls(
            page=page,
            page_size=page_size,
            total_items=total_items,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_previous=page > 1,
        )


# ══════════════════════════════════════════════════════════════════════════════
#  Error Response
# ══════════════════════════════════════════════════════════════════════════════

class ErrorDetail(BaseModel):
    """Structured error information."""

    code: str = Field(description="Machine-readable error code (e.g., AUTH_001)")
    message: str = Field(description="Human-readable error message")
    details: dict[str, Any] = Field(default_factory=dict, description="Additional context")


class ErrorResponse(BaseModel):
    """Standard error response envelope — matches exception handler output."""

    success: bool = False
    error: ErrorDetail
    request_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ══════════════════════════════════════════════════════════════════════════════
#  Health Check
# ══════════════════════════════════════════════════════════════════════════════

class DependencyHealth(BaseModel):
    """Health status of a single infrastructure dependency."""

    name: str
    status: str = Field(description="healthy | degraded | unhealthy")
    latency_ms: Optional[float] = None
    details: Optional[str] = None


class HealthStatus(BaseModel):
    """
    Comprehensive system health status.

    Used by /health/ready endpoint (Kubernetes readiness probe).
    Returns 200 if status is 'healthy', 503 otherwise.
    """

    status: str = Field(description="healthy | degraded | unhealthy")
    version: str
    environment: str
    uptime_seconds: float
    dependencies: list[DependencyHealth] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class LivenessStatus(BaseModel):
    """
    Simple liveness check — just confirms the process is running.
    Used by /health/live endpoint (Kubernetes liveness probe).
    """

    status: str = "alive"
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ══════════════════════════════════════════════════════════════════════════════
#  Sort / Filter
# ══════════════════════════════════════════════════════════════════════════════

class SortParams(BaseModel):
    """Common sort parameters for list endpoints."""

    sort_by: str = Field("created_at", description="Field to sort by")
    sort_order: str = Field("desc", pattern="^(asc|desc)$", description="Sort direction")


class DateRangeFilter(BaseModel):
    """Date range filter for time-series data endpoints."""

    start_date: Optional[datetime] = Field(None, description="Start of range (inclusive)")
    end_date: Optional[datetime] = Field(None, description="End of range (inclusive)")

    def validate_range(self) -> None:
        """Raise ValueError if end_date is before start_date."""
        if self.start_date and self.end_date:
            if self.end_date < self.start_date:
                raise ValueError("end_date must be after start_date")


# ── Compatibility Alias ───────────────────────────────────────────────────────

class PaginatedResponse(BaseModel, Generic[DataT]):
    """Simple paginated response used by alert and report routers."""

    success: bool = True
    data: list[DataT]
    total: int
    limit: int
    offset: int
    message: str = "OK"
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(from_attributes=True)
