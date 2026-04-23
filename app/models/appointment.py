import uuid
from uuid import UUID as PyUUID
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base

# 1. Estados exactos del nuevo flujo
AppointmentStatus = Literal[
    "pending_doctor_proposal",  # Paciente solicitó, espera que el Dr. ponga fecha/hora
    "pending_patient_approval", # Dr. propuso, espera confirmación del paciente
    "scheduled",                # Paciente aceptó la propuesta
    "canceled",                 # Paciente rechazó (o Dr. canceló)
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
    patient_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    appointment_date = Column(DateTime(timezone=True), nullable=True, index=True)
    end_date = Column(DateTime(timezone=True), nullable=True)
    
    status = Column(String(50), nullable=False, default="pending_doctor_proposal", index=True)
    reason = Column(Text, nullable=False, default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    doctor = relationship("User", foreign_keys=[doctor_id])
    patient = relationship("User", foreign_keys=[patient_id])


# --- DTOs (Pydantic Models) ---

# EL QUE FALTABA: Para cuando el doctor crea la cita desde cero
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
    proposed_start_at: datetime = Field(..., description="Día y hora propuesta por el doctor")
    duration_minutes: int = Field(default=30, ge=15, le=240)
    notes: Optional[str] = None

class AppointmentPatientRespondRequest(BaseModel):
    action: Literal["accept", "reject"] = Field(..., description="Si rechaza, el status pasa a canceled")

class AppointmentResponse(BaseModel):
    # Usamos PyUUID para que Pydantic lo reconozca como tipo nativo de Python
    id: PyUUID
    doctor_id: PyUUID
    patient_id: PyUUID
    status: str # Lo dejamos en str para evitar choques con data vieja en BD
    reason: str
    appointment_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    created_at: datetime
    
    # Configuración para Pydantic v2 (resuelve el error de validación)
    model_config = ConfigDict(
        from_attributes=True,
        arbitrary_types_allowed=True
    )