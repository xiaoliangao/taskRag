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
import socket
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


class _ResilientSMTP_SSL(smtplib.SMTP_SSL):
    """SMTP_SSL that walks every IPv4 result from getaddrinfo until one connects.

    Gmail's DNS round-robin returns several A records; from networks where some
    Google IPs are reachable and some are not (CN → smtp.gmail.com is the
    canonical case), the stock SMTP_SSL gives up after the first failure. This
    subclass keeps trying so a single send-attempt has many chances.
    """

    def _get_socket(self, host: str, port: int, timeout):
        infos = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)
        last_exc: Exception | None = None
        for _af, _st, _pr, _cn, sa in infos:
            try:
                sock = socket.create_connection(
                    sa, timeout=timeout, source_address=self.source_address
                )
                return self.context.wrap_socket(sock, server_hostname=host)
            except OSError as exc:
                last_exc = exc
                log.debug("SMTP connect failed for %s: %s — trying next", sa[0], exc)
                continue
        raise last_exc or OSError(f"no reachable A record for {host}:{port}")


class _ResilientSMTP(smtplib.SMTP):
    """Plain SMTP with the same IPv4-iteration behavior, for port 587 STARTTLS."""

    def _get_socket(self, host: str, port: int, timeout):
        infos = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)
        last_exc: Exception | None = None
        for _af, _st, _pr, _cn, sa in infos:
            try:
                return socket.create_connection(
                    sa, timeout=timeout, source_address=self.source_address
                )
            except OSError as exc:
                last_exc = exc
                continue
        raise last_exc or OSError(f"no reachable A record for {host}:{port}")


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
        with _ResilientSMTP_SSL(host, port, timeout=15) as smtp:
            smtp.login(settings.gmail_username, settings.gmail_app_password)
            smtp.sendmail(settings.email_from, [to], msg.as_string())
    else:
        with _ResilientSMTP(host, port, timeout=15) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(settings.gmail_username, settings.gmail_app_password)
            smtp.sendmail(settings.email_from, [to], msg.as_string())

    log.info("email sent to=%s subject=%s", to, subject)
    return SentMail(to=to, subject=subject)
