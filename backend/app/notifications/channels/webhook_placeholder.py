from __future__ import annotations

from app.core.constants import ChannelStatus
from app.db.models.notification import Notification
from app.db.models.user import User
from app.notifications.channels.inapp import ChannelResult


class WebhookChannel:
    """Placeholder for v2 — always returns skipped."""

    name = "webhook"

    def send(self, user: User, notification: Notification) -> ChannelResult:
        return ChannelResult(self.name, ChannelStatus.SKIPPED.value, "webhook channel reserved for v2")
