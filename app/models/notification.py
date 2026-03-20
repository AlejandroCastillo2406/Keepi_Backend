import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import Column, Date, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


# Modelo SQLAlchemy para la tabla de notificaciones
class Notification(Base):
    __tablename__ = "notifications"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    title = Column(String(255), nullable=False)
    type = Column(String(50), nullable=False, default="info")

    target_date = Column(Date, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Relación con usuario
    user = relationship("User", back_populates="notifications")
    
    def __repr__(self):
        return f"<Notification(id={self.id}, user_id={self.user_id}, title={self.title})>"

# Modelos Pydantic para la API
class NotificationBase(BaseModel):
    """Modelo base para notificación"""
    title: str
    type: str = "info"
    document_id: Optional[str] = None
    target_date: Optional[date] = None

class NotificationCreate(NotificationBase):
    """Modelo para crear notificación"""
    pass

class NotificationResponse(NotificationBase):
    """Modelo de respuesta para notificación"""
    id: str
    user_id: str
    document_id: Optional[str] = None
    target_date: Optional[date] = None
    created_at: datetime
    
    class Config:
        from_attributes = True

from typing import ClassVar


class NotificationType(BaseModel):
    """Tipos de notificación disponibles"""
    INFO: ClassVar[str] = "info"
    WARNING: ClassVar[str] = "warning"
    ERROR: ClassVar[str] = "error"
    SUCCESS: ClassVar[str] = "success"
    EXPIRY: ClassVar[str] = "expiry"
    SECURITY: ClassVar[str] = "security"