from __future__ import annotations

import logging
from typing import Iterable

from sqlalchemy.orm import Session

from app.db.models.notification import Notification, NotificationDelivery
from app.db.models.user import User
from app.notifications.channels.email import EmailChannel
from app.notifications.channels.inapp import ChannelResult, InAppChannel
from app.notifications.channels.webhook_placeholder import WebhookChannel

log = logging.getLogger(__name__)


def _default_channels() -> Iterable:
    return (InAppChannel(), EmailChannel(), WebhookChannel())


def dispatch_notification_sync(db: Session, notification: Notification) -> list[dict]:
    user = db.get(User, notification.user_id)
    if not user:
        log.warning("dispatch_notification_sync: user %s missing", notification.user_id)
        return []

    results: list[ChannelResult] = []
    for ch in _default_channels():
        try:
            r = ch.send(user, notification)
        except Exception as exc:
            log.exception("notification channel %s crashed: %s", ch.name, exc)
            r = ChannelResult(ch.name, "failed", str(exc)[:300])
        results.append(r)
        db.add(
            NotificationDelivery(
                notification_id=notification.id,
                channel=r.channel,
                status=r.status,
                error_msg=r.error_msg,
            )
        )
    db.commit()
    return [dict(channel=r.channel, status=r.status, error_msg=r.error_msg) for r in results]
