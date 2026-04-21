import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base

AppointmentStatus = Literal[
    "pending_patient_confirmation",
    "pending_doctor_review",
    "counter_proposed_by_doctor",
    "confirmed",
]
ProposedBy = Literal["doctor", "patient"]


class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    created_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    patient_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    appointment_date = Column(DateTime(timezone=True), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="pending_patient", index=True)
    reason = Column(Text, nullable=False, default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    doctor = relationship("User", foreign_keys=[created_by_user_id])
    patient = relationship("User", foreign_keys=[patient_id])
    proposals = relationship(
        "AppointmentProposal",
        back_populates="appointment",
        cascade="all, delete-orphan",
        order_by="AppointmentProposal.created_at.asc()",
    )


class AppointmentProposal(Base):
    __tablename__ = "appointment_proposals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    appointment_id = Column(
        UUID(as_uuid=True),
        ForeignKey("appointments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    proposed_by = Column(String(20), nullable=False)
    start_at = Column(DateTime(timezone=True), nullable=False)
    end_at = Column(DateTime(timezone=True), nullable=False)
    notes = Column(Text, nullable=True)
    sequence = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    appointment = relationship("Appointment", back_populates="proposals")


class AppointmentCreateRequest(BaseModel):
    patient_id: str
    appointment_date: datetime
    reason: str = Field(default="Consulta médica")
    duration_minutes: int = Field(default=30, ge=15, le=240)
    notes: Optional[str] = None


class AppointmentActionRequest(BaseModel):
    proposed_start_at: Optional[datetime] = None
    duration_minutes: int = Field(default=30, ge=15, le=240)
    notes: Optional[str] = None


class AppointmentResponse(BaseModel):
    id: str
    doctor_id: str
    patient_id: str
    status: str
    reason: str
    current_start_at: datetime
    current_end_at: datetime
    proposed_by: str
    version: int
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class AppointmentProposalResponse(BaseModel):
    id: str
    appointment_id: str
    proposed_by: str
    start_at: datetime
    end_at: datetime
    notes: Optional[str] = None
    sequence: int
    created_at: datetime


class AppointmentWithHistoryResponse(AppointmentResponse):
    proposals: list[AppointmentProposalResponse] = Field(default_factory=list)
