from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.notificaciones.notification_service import NotificationService


def get_notification_service(db: Session = Depends(get_db)) -> NotificationService:
    return NotificationService(db)
