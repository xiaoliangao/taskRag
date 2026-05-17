from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from jinja2 import Template

from app.core.config import get_settings
from app.core.constants import ChannelStatus
from app.db.models.notification import Notification
from app.db.models.user import User
from app.notifications.channels.inapp import ChannelResult

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
    <p style="font-size:12px;color:#999;">— TaskRAG Demo</p>
  </body>
</html>
"""
)


class EmailChannel:
    name = "email"

    def send(self, user: User, notification: Notification) -> ChannelResult:
        settings = get_settings()
        user_settings = user.settings_json or {}
        if not user_settings.get("email_notifications_enabled", True):
            return ChannelResult(self.name, ChannelStatus.SKIPPED.value, "user opted out")
        if not (settings.gmail_username and settings.gmail_app_password and settings.email_from):
            return ChannelResult(self.name, ChannelStatus.SKIPPED.value, "smtp not configured")

        try:
            html = _TEMPLATE.render(
                title=notification.title,
                body=notification.body,
                payload=notification.payload_json,
            )
            msg = MIMEMultipart("alternative")
            msg["Subject"] = notification.title
            msg["From"] = settings.email_from
            msg["To"] = user.email
            msg.attach(MIMEText(notification.body, "plain", "utf-8"))
            msg.attach(MIMEText(html, "html", "utf-8"))

            with smtplib.SMTP(settings.gmail_smtp_host, settings.gmail_smtp_port, timeout=15) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.login(settings.gmail_username, settings.gmail_app_password)
                smtp.sendmail(settings.email_from, [user.email], msg.as_string())
            return ChannelResult(self.name, ChannelStatus.SUCCESS.value)
        except Exception as exc:
            log.warning("Email send failed: %s", exc)
            return ChannelResult(self.name, ChannelStatus.FAILED.value, str(exc)[:300])
