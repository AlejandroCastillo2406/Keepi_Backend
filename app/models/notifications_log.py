import uuid
from sqlalchemy import Column

from sqlalchemy import Date, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.sql import func

from app.core.database import Base


class NotificationsLog(Base):
    __tablename__ = "notifications_logs"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(PG_UUID(as_uuid=True), nullable=False)
    document_id = Column(PG_UUID(as_uuid=True), nullable=False)

    notification_type = Column(String(50), nullable=False)
    target_date = Column(Date, nullable=False)

    days_before = Column(Integer, nullable=True)
    email_to = Column(String(255), nullable=True)
    ses_message_id = Column(String(255), nullable=True)

    sent_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return (
            "<NotificationsLog(user_id="
            f"{self.user_id}, document_id={self.document_id}, type={self.notification_type}, target_date={self.target_date})>"
        )

