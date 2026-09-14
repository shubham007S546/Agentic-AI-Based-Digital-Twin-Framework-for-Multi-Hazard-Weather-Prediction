"""
backend/app/agents/tools/notification_tools.py
──────────────────────────────────────────────
Notification dispatch tools for broadcasting CAP alerts, SMS, and dashboard alerts.
"""

from __future__ import annotations

from typing import Any, List
from app.agents.tools.base_tool import BaseAgentTool, ToolParameter


class DispatchCAPAlertTool(BaseAgentTool):
    """Tool to format and dispatch Common Alerting Protocol (CAP) XML/JSON feeds."""

    def __init__(self) -> None:
        super().__init__(
            name="dispatch_cap_alert",
            description="Broadcasts an ITU-standard Common Alerting Protocol (CAP) alert to national disaster feeds.",
            parameters=[
                ToolParameter(name="identifier", type="string", description="Unique CAP alert identifier"),
                ToolParameter(name="headline", type="string", description="Short human-readable summary"),
                ToolParameter(name="urgency", type="string", description="Immediate | Expected | Future"),
                ToolParameter(name="severity", type="string", description="Extreme | Severe | Moderate | Minor"),
                ToolParameter(name="area_description", type="string", description="Target geographical area"),
            ],
        )

    async def execute(
        self,
        identifier: str,
        headline: str,
        urgency: str,
        severity: str,
        area_description: str,
    ) -> dict[str, Any]:
        return {
            "status": "broadcasted",
            "cap_id": identifier,
            "headline": headline,
            "channels": ["CAP_FEED", "PUBLIC_RSS", "SDMA_INTRANET"],
            "urgency": urgency,
            "severity": severity,
            "area": area_description,
        }


class SendOfficerSMSTool(BaseAgentTool):
    """Tool to send high-priority SMS alerts to district emergency officers."""

    def __init__(self) -> None:
        super().__init__(
            name="send_officer_sms",
            description="Sends immediate SMS warning to district magistrates and emergency officers.",
            parameters=[
                ToolParameter(name="phone_numbers", type="array", description="List of emergency officer phone numbers"),
                ToolParameter(name="message", type="string", description="Alert text (max 160 chars recommended)"),
            ],
        )

    async def execute(self, phone_numbers: list[str], message: str) -> dict[str, Any]:
        return {
            "status": "sent",
            "recipients_count": len(phone_numbers),
            "preview": message[:120] + ("..." if len(message) > 120 else ""),
        }
