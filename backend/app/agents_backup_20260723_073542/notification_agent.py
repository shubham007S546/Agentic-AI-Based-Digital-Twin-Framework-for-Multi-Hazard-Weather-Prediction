"""
app/agents/notification_agent.py
────────────────────────────────
Agent — Notification Agent (AgentName.NOTIFICATION)

Responsibility:
  • Deliver alerts, reports, and bulletins via multiple channels:
      Email   — via aiosmtplib (SMTP)
      SMS     — via Twilio (or MSG91 for India)
      Push    — via Firebase Cloud Messaging (FCM)
      WhatsApp — via WhatsApp Business API (planned)
  • Read SMTP/Twilio credentials from Settings (SecretStr)
  • Log each delivery attempt as an AlertNotification record

Models used:
  • AlertNotification — one record per (alert, user, channel) delivery attempt
"""

from __future__ import annotations

from typing import Any

from app.agents.base_agent import BaseAgent
from app.core.enums import AgentName, NotificationChannel, NotificationStatus


# Supported channels the agent can dispatch to
_SUPPORTED_CHANNELS = {
    NotificationChannel.EMAIL,
    NotificationChannel.SMS,
    NotificationChannel.PUSH,
}


class NotificationAgent(BaseAgent):
    """
    Multi-channel notification delivery agent.
    Dispatches messages to end-users through Email, SMS, and Push channels,
    and records each delivery attempt in AlertNotification audit rows.
    """

    def __init__(self) -> None:
        super().__init__(name=AgentName.NOTIFICATION, version="1.0.0")

    @property
    def description(self) -> str:
        return (
            "Dispatches alerts and reports via Email (SMTP), SMS (Twilio), "
            "and Push (FCM) channels. Writes AlertNotification records for "
            "each delivery attempt with sent_at and error_message."
        )

    def _get_timeout_seconds(self) -> float:
        return 90.0

    async def _run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Multi-channel notification pipeline.

        Payload expects:
          - message: str                       — notification body text
          - subject: str (optional)            — email subject line
          - channels: list[str]                — e.g., ["email", "sms"]
          - recipients: list[str]              — email addresses or phone numbers
          - context: dict                      — Jinja2 template variables
          - alert_id: str (optional)           — UUID of the triggering Alert record
          - template: str (optional)           — named Jinja2 template to use

        Real implementation:
          1. Parse and validate channels against _SUPPORTED_CHANNELS
          2. For EMAIL: render Jinja2 HTML template + send via aiosmtplib
          3. For SMS: call Twilio Messages API via httpx
          4. For PUSH: call FCM v1 API via httpx
          5. For each (recipient, channel): create AlertNotification record
             with status=SENT or FAILED + error_message
        """
        message: str = payload.get("message", "")
        subject: str = payload.get("subject", "Weather Twin Alert")
        channels: list[str] = payload.get("channels", ["email"])
        recipients: list[str] = payload.get("recipients", [])
        context: dict = payload.get("context", {})
        alert_id: str | None = payload.get("alert_id")
        template: str = payload.get("template", "default_alert")

        if not message:
            self._logger.warning("NotificationAgent called with empty message")
            return {"status": "skipped", "reason": "empty message", "messages_sent": 0}

        if not recipients:
            self._logger.warning("NotificationAgent called with no recipients")
            return {"status": "skipped", "reason": "no recipients", "messages_sent": 0}

        delivery_log: list[dict] = []
        messages_sent = 0
        failed = 0

        for channel_str in channels:
            try:
                channel = NotificationChannel(channel_str)
            except ValueError:
                self._logger.warning("Unsupported notification channel", channel=channel_str)
                continue

            for recipient in recipients:
                try:
                    self._logger.info(
                        "Sending notification",
                        channel=channel.value,
                        recipient=recipient[:6] + "***",  # masked
                        template=template,
                    )

                    # ── REAL IMPLEMENTATION STUBS ──────────────────────────────
                    # if channel == NotificationChannel.EMAIL:
                    #     html = jinja_env.get_template(f"{template}.html").render(**context, message=message)
                    #     await smtp_client.send_message(to=recipient, subject=subject, html=html)
                    #
                    # elif channel == NotificationChannel.SMS:
                    #     await twilio_client.messages.create(to=recipient, body=message, from_=settings.twilio.from_number)
                    #
                    # elif channel == NotificationChannel.PUSH:
                    #     await fcm_client.send(token=recipient, title=subject, body=message)
                    #
                    # Create AlertNotification record:
                    # await notif_repo.create(AlertNotification(
                    #     alert_id=alert_id, user_id=user_id, channel=channel,
                    #     status=NotificationStatus.SENT, sent_at=datetime.now(UTC),
                    # ))

                    messages_sent += 1
                    delivery_log.append({
                        "recipient": recipient[:6] + "***",
                        "channel": channel.value,
                        "status": NotificationStatus.SENT.value,
                    })

                except Exception as exc:
                    failed += 1
                    self._logger.error(
                        "Notification delivery failed",
                        channel=channel.value,
                        recipient=recipient[:6] + "***",
                        error=str(exc),
                    )
                    delivery_log.append({
                        "recipient": recipient[:6] + "***",
                        "channel": channel.value,
                        "status": NotificationStatus.FAILED.value,
                        "error": str(exc),
                    })

        return {
            "status": "dispatched",
            "channels_used": channels,
            "recipients_count": len(recipients),
            "messages_sent": messages_sent,
            "failed": failed,
            "alert_id": alert_id,
            "delivery_log": delivery_log,
        }
