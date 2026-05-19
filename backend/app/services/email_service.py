"""Reusable SMTP sender.

Used by:
- Notification email channel (`notifications/channels/email.py`)
- Auth verification codes (`services/verification_code_service.py`)
- Admin broadcast (`api/routes/admin.py`)

Port semantics: 465 → SMTP_SSL (implicit TLS), anything else → SMTP + STARTTLS.
This matters because some networks (notably Tencent Cloud → Gmail) only have a
clear path on 465.
"""
from __future__ import annotations

import logging
import smtplib
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import get_settings

log = logging.getLogger(__name__)


class EmailNotConfiguredError(RuntimeError):
    """Raised when SMTP credentials are missing. Callers can decide to fall back
    (e.g., log the verification code) instead of treating it as a hard failure."""


@dataclass
class SentMail:
    to: str
    subject: str


def is_configured() -> bool:
    s = get_settings()
    return bool(s.gmail_username and s.gmail_app_password and s.email_from)


def send_email(
    *,
    to: str,
    subject: str,
    text_body: str,
    html_body: str | None = None,
) -> SentMail:
    """Send a single email synchronously. Raises EmailNotConfiguredError when
    SMTP creds are absent and any smtplib exception otherwise."""
    settings = get_settings()
    if not is_configured():
        raise EmailNotConfiguredError("SMTP credentials are not set")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.email_from
    msg["To"] = to
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    if html_body:
        msg.attach(MIMEText(html_body, "html", "utf-8"))

    host = settings.gmail_smtp_host
    port = settings.gmail_smtp_port
    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=15) as smtp:
            smtp.login(settings.gmail_username, settings.gmail_app_password)
            smtp.sendmail(settings.email_from, [to], msg.as_string())
    else:
        with smtplib.SMTP(host, port, timeout=15) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(settings.gmail_username, settings.gmail_app_password)
            smtp.sendmail(settings.email_from, [to], msg.as_string())

    log.info("email sent to=%s subject=%s", to, subject)
    return SentMail(to=to, subject=subject)
