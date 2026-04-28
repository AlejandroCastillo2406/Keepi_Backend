from __future__ import annotations

import uuid
from typing import Any, List, Optional

from sqlalchemy.orm import Session

from app.models.notification import Notification


class NotificationRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def list_by_user(self, user_id: Any) -> List[Notification]:
        uid = uuid.UUID(str(user_id))
        return (
            self._db.query(Notification)
            .filter(Notification.user_id == uid)
            .order_by(Notification.created_at.desc())
            .all()
        )

    def get_by_id_for_user(
        self, notification_id: str, user_id: Any
    ) -> Optional[Notification]:
        uid = uuid.UUID(str(user_id))
        try:
            nid = uuid.UUID(str(notification_id))
        except (ValueError, TypeError):
            return None
        return (
            self._db.query(Notification)
            .filter(Notification.id == nid, Notification.user_id == uid)
            .first()
        )

    def add(self, notification: Notification) -> Notification:
        self._db.add(notification)
        self._db.commit()
        self._db.refresh(notification)
        return notification

    def delete(self, notification: Notification) -> None:
        self._db.delete(notification)
        self._db.commit()
