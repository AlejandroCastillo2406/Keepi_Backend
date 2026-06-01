import uuid
from datetime import datetime

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.core.database import Base


class DoctorTimelineNote(Base):
    __tablename__ = "doctor_timeline_notes"
    __table_args__ = (
        UniqueConstraint(
            "patient_id",
            "timeline_event_id",
            name="uq_doctor_timeline_note_patient_event",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
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
    timeline_event_id = Column(String(120), nullable=False, index=True)
    event_type = Column(String(40), nullable=False, default="")
    s3_key = Column(String(500), nullable=False)
    content_preview = Column(Text, nullable=False, default="")
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DoctorTimelineNoteResponse(BaseModel):
    event_id: str
    content: str
    created_at: datetime
    doctor_id: str


class DoctorTimelineNoteCreate(BaseModel):
    doctor_note: str = Field(..., min_length=1, max_length=8000)
    event_type: str | None = Field(None, max_length=40)
