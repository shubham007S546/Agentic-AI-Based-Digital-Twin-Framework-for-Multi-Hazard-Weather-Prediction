"""
app/api/v1/routers/report_router.py
───────────────────────────────────
Report API endpoints.
"""

from typing import Annotated, Optional
import uuid

from fastapi import APIRouter, Depends, Path, Query, status

from app.api.v1.controllers.report_controller import ReportController
from app.core.enums import District
from app.dependencies.auth import CurrentUserToken, require_admin
from app.schemas.common import ApiResponse, PaginatedResponse
from app.schemas.report import ReportCreateRequest, ReportResponse


router = APIRouter()


@router.get(
    "",
    response_model=PaginatedResponse[ReportResponse],
    summary="Get all reports (paginated)",
)
async def get_all_reports(
    token_data: CurrentUserToken,
    controller: Annotated[ReportController, Depends()],
    district: Optional[District] = Query(None, description="Filter by district"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> PaginatedResponse[ReportResponse]:
    """Fetch a paginated list of all generated reports."""
    reports = await controller.get_all_reports(limit, offset, district)
    return PaginatedResponse(
        data=reports,
        total=len(reports),
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{report_id}",
    response_model=ApiResponse[ReportResponse],
    summary="Get report by ID",
)
async def get_report(
    report_id: Annotated[uuid.UUID, Path(...)],
    token_data: CurrentUserToken,
    controller: Annotated[ReportController, Depends()],
) -> ApiResponse[ReportResponse]:
    """Fetch details and download link for a specific report."""
    report = await controller.get_report(report_id)
    return ApiResponse(data=report)


@router.post(
    "",
    response_model=ApiResponse[ReportResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Request a new report",
)
async def request_report(
    payload: ReportCreateRequest,
    token_data: CurrentUserToken,
    controller: Annotated[ReportController, Depends()],
) -> ApiResponse[ReportResponse]:
    """Queue a new analytical report for generation."""
    report = await controller.request_report(payload, requested_by=uuid.UUID(token_data.user_id))
    return ApiResponse(
        data=report,
        message="Report generation requested",
    )
