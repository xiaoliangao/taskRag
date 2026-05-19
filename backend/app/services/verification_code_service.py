"""Email verification codes for registration.

Strict rules:
- 6 digit numeric code, 10 minute TTL
- 60s send cooldown per email
- 5 sends per email per 24h
- Code consumed (deleted) on successful verify

Storage: Redis. Falls back to logging the code when SMTP is not configured,
so the demo/dev flow still works before Gmail credentials are filled in.
"""
from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass

from app.core.config import get_settings
from app.core.errors import RateLimitedError, ValidationError
from app.services.email_service import (
    EmailNotConfiguredError,
    is_configured,
    send_email,
)

log = logging.getLogger(__name__)

CODE_TTL_S = 600          # 10 minutes
COOLDOWN_S = 60           # between sends for the same email
DAILY_LIMIT = 5           # per-email daily send cap
DAILY_WINDOW_S = 24 * 60 * 60


def _redis():
    try:
        import redis

        return redis.Redis.from_url(get_settings().redis_url, decode_responses=True)
    except Exception:  # pragma: no cover
        return None


def _code_key(email: str) -> str:
    return f"auth:vcode:code:{email.lower()}"


def _cooldown_key(email: str) -> str:
    return f"auth:vcode:cooldown:{email.lower()}"


def _daily_key(email: str) -> str:
    return f"auth:vcode:daily:{email.lower()}"


@dataclass
class SendResult:
    cooldown_s: int
    delivery: str  # "email" | "log"


def generate_and_send_code(email: str) -> SendResult:
    cli = _redis()
    if cli is None:
        raise ValidationError("Verification code service unavailable")

    # cooldown check
    cooldown_ttl = cli.ttl(_cooldown_key(email))
    if cooldown_ttl and cooldown_ttl > 0:
        raise RateLimitedError(f"Please wait {cooldown_ttl}s before requesting a new code")

    # daily cap
    daily_count = int(cli.get(_daily_key(email)) or 0)
    if daily_count >= DAILY_LIMIT:
        raise RateLimitedError(f"Daily verification-code limit reached ({DAILY_LIMIT}/day)")

    code = f"{secrets.randbelow(1_000_000):06d}"

    cli.setex(_code_key(email), CODE_TTL_S, code)
    cli.setex(_cooldown_key(email), COOLDOWN_S, "1")
    # Increment daily counter, set TTL only on first increment of the window.
    new_count = cli.incr(_daily_key(email))
    if new_count == 1:
        cli.expire(_daily_key(email), DAILY_WINDOW_S)

    # Send via email if configured; otherwise log it (dev/demo mode).
    delivery = "email"
    if is_configured():
        try:
            send_email(
                to=email,
                subject="TaskRAG · 注册验证码",
                text_body=f"您的验证码是 {code},10 分钟内有效。如果不是您本人操作请忽略此邮件。",
                html_body=_render_html(code),
            )
        except EmailNotConfiguredError:
            delivery = "log"
            log.warning("[VERIFICATION CODE] email=%s code=%s (SMTP not configured)", email, code)
        except Exception as exc:
            # Don't reveal SMTP failure details to caller; just degrade to log.
            log.warning("verification email send failed for %s: %s", email, exc)
            log.warning("[VERIFICATION CODE] email=%s code=%s (SMTP error)", email, code)
            delivery = "log"
    else:
        delivery = "log"
        log.warning("[VERIFICATION CODE] email=%s code=%s (SMTP not configured)", email, code)

    return SendResult(cooldown_s=COOLDOWN_S, delivery=delivery)


def verify_and_consume(email: str, code: str) -> None:
    """Raise ValidationError on bad/expired code. On success, delete the code so
    it can't be replayed."""
    cli = _redis()
    if cli is None:
        raise ValidationError("Verification code service unavailable")
    stored = cli.get(_code_key(email))
    if not stored:
        raise ValidationError("验证码已过期,请重新获取")
    if stored != code:
        raise ValidationError("验证码不正确")
    cli.delete(_code_key(email))


def _render_html(code: str) -> str:
    return f"""
<html>
  <body style="font-family: -apple-system, Helvetica, Arial, sans-serif; color: #222; padding: 24px;">
    <h2 style="margin: 0 0 8px;">TaskRAG 注册验证码</h2>
    <p style="color: #555; margin: 0 0 24px;">请在 10 分钟内回到注册页填入下面的 6 位验证码:</p>
    <div style="font-family: 'JetBrains Mono', Menlo, Consolas, monospace; font-size: 30px; letter-spacing: 0.4em; font-weight: 600; background: #f6f8fa; padding: 16px 24px; border-radius: 8px; display: inline-block;">{code}</div>
    <p style="color: #999; font-size: 12px; margin-top: 28px;">如果不是您本人操作,请忽略此邮件,无需任何处理。</p>
  </body>
</html>
"""
