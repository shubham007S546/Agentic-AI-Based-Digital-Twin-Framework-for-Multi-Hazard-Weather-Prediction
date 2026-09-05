"""
app/api/v1/controllers/notification_controller.py
─────────────────────────────────────────────────
Notification Controller.
"""

from app.schemas.notification import NotificationDispatchRequest, NotificationDispatchResponse
from app.agents.agent_registry import get_agent_manager
from app.core.enums import AgentName, AgentTrigger


class NotificationController:
    """Controller for Notification endpoints."""

    async def dispatch_notification(self, request: NotificationDispatchRequest, triggered_by: str) -> NotificationDispatchResponse:
        agent_mgr = get_agent_manager()
        
        # We invoke the NotificationAgent synchronously here to get the result
        result = await agent_mgr.execute(
            agent_name=AgentName.NOTIFICATION,
            payload={
                "message": request.message,
                "channels": request.channels,
                "recipients": request.recipients,
                "context": request.context,
            },
            trigger=AgentTrigger.MANUAL,
            triggered_by=triggered_by
        )
        
        summary = result.result_summary or {}
        
        return NotificationDispatchResponse(
            status=result.status.name,
            message="Notification dispatch initiated",
            dispatched_count=summary.get("messages_sent", 0),
            channels_used=summary.get("channels_used", []),
        )
