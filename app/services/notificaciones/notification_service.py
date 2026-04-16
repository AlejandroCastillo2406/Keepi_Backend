from __future__ import annotations

from typing import Any, List, Optional

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models.notification import Notification, NotificationCreate, NotificationResponse


class NotificationService:
    """Servicio para gestión de notificaciones (PostgreSQL)."""

    def __init__(self, db: Session):
        self.db = db

    async def get_user_notifications(self, user_id: Any) -> List[NotificationResponse]:
        """Obtener todas las notificaciones de un usuario."""
        notifications = (
            self.db.query(Notification)
            .filter(Notification.user_id == user_id)
            .order_by(desc(Notification.created_at))
            .all()
        )
        return [self._to_response(n) for n in notifications]

    async def get_notification_by_id(
        self, notification_id: str, user_id: Any
    ) -> Optional[NotificationResponse]:
        """Obtener notificación por ID."""
        notification = (
            self.db.query(Notification)
            .filter(Notification.id == notification_id)
            .filter(Notification.user_id == user_id)
            .first()
        )
        if notification is None:
            return None
        return self._to_response(notification)

    async def create_notification(
        self, user_id: Any, notification_data: NotificationCreate
    ) -> NotificationResponse:
        """Crear nueva notificación."""
        notification = Notification(
            user_id=user_id,
            document_id=notification_data.document_id,
            title=notification_data.title,
            message=notification_data.message or notification_data.title,
            type=notification_data.type,
            target_date=notification_data.target_date,
            payload=notification_data.payload or {},
            read=notification_data.read or False,
            read_at=notification_data.read_at,
        )
        self.db.add(notification)
        self.db.commit()
        self.db.refresh(notification)
        return self._to_response(notification)

    async def delete_notification(self, notification_id: str, user_id: Any) -> bool:
        """Eliminar notificación."""
        notification = (
            self.db.query(Notification)
            .filter(Notification.id == notification_id)
            .filter(Notification.user_id == user_id)
            .first()
        )
        if notification is None:
            return False

        self.db.delete(notification)
        self.db.commit()
        return True

    @staticmethod
    def _to_response(notification: Notification) -> NotificationResponse:
        return NotificationResponse(
            id=str(notification.id),
            user_id=str(notification.user_id),
            document_id=str(notification.document_id) if notification.document_id else None,
            title=notification.title,
            message=notification.message,
            type=notification.type,
            target_date=notification.target_date,
            payload=notification.payload or {},
            read=bool(notification.read),
            read_at=notification.read_at,
            created_at=notification.created_at,
        )

