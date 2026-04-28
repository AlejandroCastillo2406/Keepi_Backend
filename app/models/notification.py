import uuid
from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, Field
from sqlalchemy import Column, Date, DateTime, ForeignKey, JSON, String, Text, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    type = Column(String(50), nullable=False, default="info")

    target_date = Column(Date, nullable=True)
    payload = Column(JSON, nullable=False, default=dict)
    read = Column(Boolean, nullable=False, default=False)
    read_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user = relationship("User", back_populates="notifications")

    def __repr__(self):
        return (
            f"<Notification(id={self.id}, user_id={self.user_id}, title={self.title})>"
        )


class NotificationBase(BaseModel):
    title: str
    message: str = ""
    type: str = "info"
    document_id: Optional[str] = None
    target_date: Optional[date] = None
    payload: Optional[dict] = None
    read: Optional[bool] = False
    read_at: Optional[datetime] = None


class NotificationCreate(NotificationBase):
    pass


class NotificationResponse(NotificationBase):
    id: str
    user_id: str
    document_id: Optional[str] = None
    target_date: Optional[date] = None
    payload: dict = {}
    read: bool = False
    read_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


from typing import ClassVar


class NotificationType(BaseModel):
    INFO: ClassVar[str] = "info"
    WARNING: ClassVar[str] = "warning"
    ERROR: ClassVar[str] = "error"
    SUCCESS: ClassVar[str] = "success"
    EXPIRY: ClassVar[str] = "expiry"
    SECURITY: ClassVar[str] = "security"
