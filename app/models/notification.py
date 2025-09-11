from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class NotificationBase(BaseModel):
    """Modelo base para notificación"""
    title: str
    message: str
    type: str = "info"

class NotificationCreate(NotificationBase):
    """Modelo para crear notificación"""
    pass

class NotificationUpdate(BaseModel):
    """Modelo para actualizar notificación"""
    read: Optional[bool] = None

class NotificationResponse(NotificationBase):
    """Modelo de respuesta para notificación"""
    id: str
    user_id: str
    read: bool = False
    created_at: datetime
    read_at: Optional[datetime] = None

from typing import ClassVar

class NotificationType(BaseModel):
    """Tipos de notificación disponibles"""
    INFO: ClassVar[str] = "info"
    WARNING: ClassVar[str] = "warning"
    ERROR: ClassVar[str] = "error"
    SUCCESS: ClassVar[str] = "success"
    EXPIRY: ClassVar[str] = "expiry"
    SECURITY: ClassVar[str] = "security"
