import uuid
from datetime import datetime, time
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Time,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class DoctorAvailabilityRule(Base):
    __tablename__ = "doctor_availability_rules"
    __table_args__ = (
        UniqueConstraint(
            "doctor_id", "weekday", name="uq_doctor_availability_doctor_weekday"
        ),
    )

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    doctor_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    weekday = Column(SmallInteger, nullable=False)  # 0=Mon … 6=Sun (ISO)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    is_enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    doctor = relationship("User", foreign_keys=[doctor_id])


class DoctorSchedulingSettings(Base):
    __tablename__ = "doctor_scheduling_settings"

    doctor_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    slot_duration_minutes = Column(Integer, nullable=False, default=30)
    timezone = Column(String(64), nullable=False, default="America/Mexico_City")
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    doctor = relationship("User", foreign_keys=[doctor_id])


class PatientSchedulingToken(Base):
    __tablename__ = "patient_scheduling_tokens"
    __table_args__ = (
        UniqueConstraint(
            "patient_id", "doctor_id", name="uq_patient_scheduling_patient_doctor"
        ),
    )

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    doctor_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash = Column(String(128), nullable=False, unique=True, index=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    patient = relationship("User", foreign_keys=[patient_id])
    doctor = relationship("User", foreign_keys=[doctor_id])


class AvailabilityRuleItem(BaseModel):
    weekday: int = Field(..., ge=0, le=6)
    start_time: str = Field(..., description="HH:MM")
    end_time: str = Field(..., description="HH:MM")
    is_enabled: bool = True

    @field_validator("start_time", "end_time")
    @classmethod
    def validate_time_format(cls, v: str) -> str:
        parts = v.strip().split(":")
        if len(parts) != 2:
            raise ValueError("Formato de hora inválido (use HH:MM)")
        h, m = int(parts[0]), int(parts[1])
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError("Hora fuera de rango")
        return f"{h:02d}:{m:02d}"


class AvailabilityRulesUpdateRequest(BaseModel):
    rules: List[AvailabilityRuleItem]


class AvailabilityRuleResponse(BaseModel):
    id: str
    weekday: int
    start_time: str
    end_time: str
    is_enabled: bool

    model_config = ConfigDict(from_attributes=True)


class SchedulingSettingsResponse(BaseModel):
    slot_duration_minutes: int
    timezone: str

    model_config = ConfigDict(from_attributes=True)


class SchedulingSettingsUpdateRequest(BaseModel):
    slot_duration_minutes: int = Field(default=30, ge=15, le=120)
    timezone: str = Field(default="America/Mexico_City", min_length=3, max_length=64)


class PublicSchedulingMetaResponse(BaseModel):
    doctor_name: str
    patient_name: str
    timezone: str
    slot_duration_minutes: int
    has_availability_rules: bool
    message: Optional[str] = None


class AvailabilitySlotResponse(BaseModel):
    start_at: datetime
    end_at: datetime


class PublicAvailabilityResponse(BaseModel):
    slots: List[AvailabilitySlotResponse]
    message: Optional[str] = None


class PublicBookAppointmentRequest(BaseModel):
    start_at: datetime
    reason: str = Field(default="", max_length=2000)


class PublicBookAppointmentResponse(BaseModel):
    appointment_id: str
    status: str
    message: str


class PatientSchedulingLinkResponse(BaseModel):
    scheduling_link: str
    patient_name: str
    message: str = ""


def parse_time_str(value: str) -> time:
    parts = value.strip().split(":")
    return time(hour=int(parts[0]), minute=int(parts[1]))
