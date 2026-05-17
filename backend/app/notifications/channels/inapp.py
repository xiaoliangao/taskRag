from __future__ import annotations

from dataclasses import dataclass

from app.core.constants import ChannelStatus
from app.db.models.notification import Notification
from app.db.models.user import User


@dataclass
class ChannelResult:
    channel: str
    status: str
    error_msg: str | None = None


class InAppChannel:
    name = "inapp"

    def send(self, user: User, notification: Notification) -> ChannelResult:
        # InApp notifications are persisted directly when the notification row
        # is created. This channel just confirms presence.
        if notification.id is None:
            return ChannelResult(self.name, ChannelStatus.FAILED.value, "notification not persisted")
        return ChannelResult(self.name, ChannelStatus.SUCCESS.value)
