"""Distribute Report, matching the diagram's "Distribute Report" step.
Deciding *whether* and to which channels is real; actually sending is
stubbed pending real provider credentials (same pattern as Agent 4's
escalation.py -- email/SMS/WhatsApp need SendGrid/Twilio/etc.)."""

from __future__ import annotations

from typing import Any, Dict, List

from .logging_config import get_logger

logger = get_logger(__name__)


def _send_stub(channel: str, report_id: str, file_path: str) -> Dict[str, Any]:
    logger.info("Would distribute report %s via %s (STUB -- no provider configured): %s",
                report_id, channel, file_path)
    return {"channel": channel, "status": "stub",
            "note": f"No {channel} provider configured -- report generated but not actually sent."}


def distribute_report(report_id: str, file_path: str, distribute: bool, channels: List[str]) -> List[Dict[str, Any]]:
    if not distribute:
        return [{"channel": "none", "status": "skipped", "note": "distribute=False in request."}]
    if not channels:
        return [{"channel": "none", "status": "skipped", "note": "No notification_channels specified."}]
    return [_send_stub(channel, report_id, file_path) for channel in channels]
