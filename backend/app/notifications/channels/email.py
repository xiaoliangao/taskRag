from __future__ import annotations

import logging

from jinja2 import Template

from app.core.constants import ChannelStatus
from app.db.models.notification import Notification
from app.db.models.user import User
from app.notifications.channels.inapp import ChannelResult
from app.services.email_service import (
    EmailNotConfiguredError,
    is_configured,
    send_email,
)

log = logging.getLogger(__name__)

_TEMPLATE = Template(
    """
<html>
  <body style="font-family: -apple-system, Helvetica, Arial, sans-serif; color: #222;">
    <h2 style="margin-bottom: 4px;">{{ title }}</h2>
    <p style="color: #555;">{{ body }}</p>
    {% if payload %}
    <pre style="background:#f6f8fa;padding:10px;border-radius:6px;overflow:auto;font-size:12px;">{{ payload }}</pre>
    {% endif %}
    <hr/>
    <p style="font-size:12px;color:#999;">— TaskRAG</p>
  </body>
</html>
"""
)


class EmailChannel:
    name = "email"

    def send(self, user: User, notification: Notification) -> ChannelResult:
        user_settings = user.settings_json or {}
        if not user_settings.get("email_notifications_enabled", True):
            return ChannelResult(self.name, ChannelStatus.SKIPPED.value, "user opted out")
        if not is_configured():
            return ChannelResult(self.name, ChannelStatus.SKIPPED.value, "smtp not configured")

        try:
            html = _TEMPLATE.render(
                title=notification.title,
                body=notification.body,
                payload=notification.payload_json,
            )
            send_email(
                to=user.email,
                subject=notification.title,
                text_body=notification.body,
                html_body=html,
            )
            return ChannelResult(self.name, ChannelStatus.SUCCESS.value)
        except EmailNotConfiguredError:
            return ChannelResult(self.name, ChannelStatus.SKIPPED.value, "smtp not configured")
        except Exception as exc:
            log.warning("Email send failed: %s", exc)
            return ChannelResult(self.name, ChannelStatus.FAILED.value, str(exc)[:300])
