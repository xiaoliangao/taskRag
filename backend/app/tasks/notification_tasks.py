from __future__ import annotations

import logging

from app.db.models.notification import Notification
from app.db.session import get_sync_sessionmaker
from app.notifications.workflow import dispatch_notification_sync
from app.tasks.celery_app import celery_app

log = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.notification_tasks.send_notification_task")
def send_notification_task(notification_id: int) -> dict:
    Session = get_sync_sessionmaker()
    with Session() as db:
        n = db.get(Notification, notification_id)
        if not n:
            return {"status": "skipped"}
        result = dispatch_notification_sync(db, n)
        return {"status": "ok", "deliveries": result}
