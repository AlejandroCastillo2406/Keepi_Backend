import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class Prescription(Base):
    __tablename__ = "prescriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    doctor_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    patient_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    source_file_name = Column(String(255), nullable=True)
    source_file_type = Column(String(100), nullable=True)
    source_s3_key = Column(String(500), nullable=True)
    extracted_text = Column(Text, nullable=True)
    status = Column(String(40), nullable=False, default="draft_ocr")
    patient_reminders_enabled = Column(Boolean, nullable=False, default=False)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    confirmed_at = Column(DateTime(timezone=True), nullable=True)

    items = relationship(
        "PrescriptionItem", back_populates="prescription", cascade="all, delete-orphan"
    )


class PrescriptionItem(Base):
    __tablename__ = "prescription_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    prescription_id = Column(
        UUID(as_uuid=True),
        ForeignKey("prescriptions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    medication = Column(String(255), nullable=False)
    every_hours = Column(Integer, nullable=True)
    duration_days = Column(Integer, nullable=True)
    route = Column(String(120), nullable=True)
    raw_payload = Column(JSON, nullable=False, default=dict)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    prescription = relationship("Prescription", back_populates="items")


class PrescriptionItemIn(BaseModel):
    medication: str = Field(..., min_length=1)
    every_hours: Optional[int] = None
    duration_days: Optional[int] = None
    route: Optional[str] = None


class PrescriptionDraftResponse(BaseModel):
    id: str
    patient_id: str
    status: str
    filename: Optional[str] = None
    extracted_text: str = ""
    items: List[PrescriptionItemIn] = []


class PrescriptionConfirmRequest(BaseModel):
    extracted_text: str = ""
    items: List[PrescriptionItemIn] = []
    ask_reminder_opt_in: bool = True


class PrescriptionPatientResponse(BaseModel):
    id: str
    doctor_name: Optional[str] = None
    status: str
    source_file_name: Optional[str] = None
    confirmed_at: Optional[datetime] = None
    reminders_enabled: bool = False
    items: List[PrescriptionItemIn] = []
