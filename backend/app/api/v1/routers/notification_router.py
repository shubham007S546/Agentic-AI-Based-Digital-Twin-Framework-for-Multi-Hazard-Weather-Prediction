"""
app/api/v1/routers/notification_router.py
─────────────────────────────────────────
Notification API endpoints.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.v1.controllers.notification_controller import NotificationController
from app.dependencies.auth import CurrentUserToken, require_admin
from app.schemas.common import ApiResponse
from app.schemas.notification import NotificationDispatchRequest, NotificationDispatchResponse

router = APIRouter()


@router.post(
    "/dispatch",
    response_model=ApiResponse[NotificationDispatchResponse],
    status_code=status.HTTP_200_OK,
    summary="Dispatch a manual notification",
    dependencies=[Depends(require_admin)],
)
async def dispatch_notification(
    payload: NotificationDispatchRequest,
    token_data: CurrentUserToken,
    controller: Annotated[NotificationController, Depends()],
) -> ApiResponse[NotificationDispatchResponse]:
    """Manually trigger the NotificationAgent to dispatch messages (Admin only)."""
    response = await controller.dispatch_notification(payload, triggered_by=token_data.user_id)
    return ApiResponse(
        data=response,
        message="Notification dispatch executed",
    )
