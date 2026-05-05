import uuid
from typing import Literal

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.core.database import Base

AnalysisUploadInvitationStatus = Literal["pending", "completed", "expired", "cancelled"]


class AnalysisRequestUploadInvitation(Base):
    __tablename__ = "analysis_request_upload_invitations"
    __table_args__ = (
        UniqueConstraint(
            "token_hash", name="uq_analysis_request_upload_invitation_token_hash"
        ),
        CheckConstraint(
            "status IN ('pending','completed','expired','cancelled')",
            name="ck_analysis_request_upload_invitation_status",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    analysis_request_id = Column(
        UUID(as_uuid=True),
        ForeignKey("analysis_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    doctor_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    patient_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    token_hash = Column(String(128), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="pending", index=True)

    patient_email_snapshot = Column(String(255), nullable=True)
    patient_name_snapshot = Column(String(255), nullable=True)

    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    used_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
