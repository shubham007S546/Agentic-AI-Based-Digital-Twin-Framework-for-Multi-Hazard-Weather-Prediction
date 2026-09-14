"""
Escalation Manager, matching the diagram's "Notify & Escalate" step. The
routing/escalation *decision* is real (based on severity); actually
dispatching a notification is stubbed, since that needs real provider
credentials (Twilio for SMS/WhatsApp, SendGrid/SES for email, Firebase for
push) which aren't part of this project yet.
"""

from __future__ import annotations

from typing import Any, Dict, List

from .config import settings
from .logging_config import get_logger

logger = get_logger(__name__)

_SEVERITY_ORDER = ["green", "yellow", "orange", "red"]


def _meets_escalation_floor(severity: str) -> bool:
    floor_idx = _SEVERITY_ORDER.index(settings.escalation_severity_floor)
    return _SEVERITY_ORDER.index(severity) >= floor_idx


def _send_notification_stub(channel: str, alert: Dict[str, Any]) -> Dict[str, Any]:
    """Real send would go here, e.g.:
        if channel == "email": sendgrid_client.send(...)
        if channel == "sms":   twilio_client.messages.create(...)
        if channel == "push":  firebase_admin.messaging.send(...)
    """
    logger.info("Would send %s notification for alert %s (STUB -- no provider configured)",
                channel, alert.get("alert_id"))
    return {
        "channel": channel, "status": "stub",
        "note": f"No {channel} provider configured -- notification logged but not actually sent.",
    }


def notify_and_escalate(alert: Dict[str, Any], notify: bool) -> tuple:
    """Returns (notifications: list[dict], escalated: bool)."""
    if not notify:
        return [{"channel": "none", "status": "skipped", "note": "notify=False in request."}], False

    severity = alert["severity"].lower()
    notifications = [_send_notification_stub(ch, alert) for ch in settings.notification_channels]

    escalated = _meets_escalation_floor(severity)
    if escalated:
        notifications.append({
            "channel": "authority_escalation", "status": "stub",
            "note": f"Severity {severity!r} meets escalation floor "
                    f"({settings.escalation_severity_floor!r}) -- would notify local disaster authorities.",
        })

    return notifications, escalated
