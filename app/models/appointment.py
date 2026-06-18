import uuid
from uuid import UUID as PyUUID
from datetime import datetime
from typing import Literal, List, Optional

from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base
from app.models.doctor_scheduling import ConsultationScheduleResponse

AppointmentStatus = Literal[
    "pending_doctor_proposal",
    "pending_patient_approval",
    "pending_doctor_approval",
    "scheduled",
    "canceled",
]


class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    doctor_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    patient_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    appointment_date = Column(DateTime(timezone=True), nullable=True, index=True)
    end_date = Column(DateTime(timezone=True), nullable=True)

    status = Column(
        String(50), nullable=False, default="pending_doctor_proposal", index=True
    )
    reason = Column(Text, nullable=False, default="")
    attendance_status = Column(String(20), nullable=True, index=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    doctor = relationship("User", foreign_keys=[doctor_id])
    patient = relationship("User", foreign_keys=[patient_id])


class AppointmentCreateRequest(BaseModel):
    patient_id: str
    appointment_date: datetime
    reason: str = ""
    duration_minutes: int = 30
    notes: Optional[str] = None


class AppointmentPatientCreateRequest(BaseModel):
    doctor_id: str
    reason: str = Field(..., description="Motivo de la consulta en texto")


class AppointmentDoctorProposeRequest(BaseModel):
    proposed_start_at: datetime = Field(
        ..., description="Día y hora propuesta por el doctor"
    )
    duration_minutes: int = Field(default=30, ge=15, le=240)
    notes: Optional[str] = None


class AppointmentPatientRespondRequest(BaseModel):
    action: Literal["accept", "reject"] = Field(
        ..., description="Si rechaza, el status pasa a canceled"
    )


class AppointmentDoctorRescheduleRequest(BaseModel):
    proposed_start_at: datetime = Field(
        ..., description="Nueva fecha y hora propuesta por el doctor"
    )
    duration_minutes: int = Field(default=30, ge=15, le=240)


class PublicAppointmentMetaResponse(BaseModel):
    patient_name: str
    doctor_name: str
    reason: str
    when_label: str
    status: str
    already_responded: bool = False
    response_action: Optional[str] = None


class PublicAppointmentRespondRequest(BaseModel):
    action: Literal["accept", "reject"]


class PublicAppointmentRespondResponse(BaseModel):
    status: str
    message: str


class AppointmentAttendanceRequest(BaseModel):
    status: Literal["attended", "no_show"] = Field(
        ..., description="Confirmación de asistencia del paciente"
    )


class AppointmentResponse(BaseModel):

    id: PyUUID
    doctor_id: PyUUID
    patient_id: PyUUID
    status: str
    reason: str
    appointment_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    attendance_status: Optional[str] = None
    created_at: datetime
    patient_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True, arbitrary_types_allowed=True)

    @classmethod
    def from_entity(cls, appt: Appointment) -> "AppointmentResponse":
        patient_name = None
        patient = getattr(appt, "patient", None)
        if patient is not None:
            patient_name = (patient.name or "").strip() or "Paciente"
        return cls(
            id=appt.id,
            doctor_id=appt.doctor_id,
            patient_id=appt.patient_id,
            status=appt.status,
            reason=appt.reason or "",
            appointment_date=appt.appointment_date,
            end_date=appt.end_date,
            attendance_status=getattr(appt, "attendance_status", None),
            created_at=appt.created_at,
            patient_name=patient_name,
        )


class DoctorCalendarResponse(BaseModel):
    appointments: List[AppointmentResponse]
    consultation_schedule: ConsultationScheduleResponse
