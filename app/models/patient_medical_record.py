"""Expediente médico del paciente (alta por médico, edición por paciente)."""

import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import Column, Date, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class PatientMedicalRecord(Base):
    __tablename__ = "patient_medical_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    created_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    date_of_birth = Column(Date, nullable=True)
    sex = Column(String(32), nullable=True)
    blood_type = Column(String(16), nullable=True)
    allergies = Column(Text, nullable=True)
    chronic_conditions = Column(Text, nullable=True)
    current_medications = Column(Text, nullable=True)
    medical_notes = Column(Text, nullable=True)
    emergency_contact_name = Column(String(255), nullable=True)
    emergency_contact_phone = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    patient = relationship("User", back_populates="medical_record", foreign_keys=[patient_user_id])
    created_by = relationship("User", foreign_keys=[created_by_user_id])


class MedicalRecordInput(BaseModel):
    """Datos del expediente al crear paciente (médico). Todos opcionales."""

    date_of_birth: Optional[date] = None
    sex: Optional[str] = Field(None, max_length=32)
    blood_type: Optional[str] = Field(None, max_length=16)
    allergies: Optional[str] = None
    chronic_conditions: Optional[str] = None
    current_medications: Optional[str] = None
    medical_notes: Optional[str] = None
    emergency_contact_name: Optional[str] = Field(None, max_length=255)
    emergency_contact_phone: Optional[str] = Field(None, max_length=64)


class MedicalRecordPatientUpdate(BaseModel):
    """Actualización por el paciente (campos opcionales)."""

    date_of_birth: Optional[date] = None
    sex: Optional[str] = Field(None, max_length=32)
    blood_type: Optional[str] = Field(None, max_length=16)
    allergies: Optional[str] = None
    chronic_conditions: Optional[str] = None
    current_medications: Optional[str] = None
    medical_notes: Optional[str] = None
    emergency_contact_name: Optional[str] = Field(None, max_length=255)
    emergency_contact_phone: Optional[str] = Field(None, max_length=64)


class MedicalRecordResponse(BaseModel):
    id: str
    patient_user_id: str
    date_of_birth: Optional[date] = None
    sex: Optional[str] = None
    blood_type: Optional[str] = None
    allergies: Optional[str] = None
    chronic_conditions: Optional[str] = None
    current_medications: Optional[str] = None
    medical_notes: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

    @classmethod
    def from_orm_record(cls, row: PatientMedicalRecord) -> "MedicalRecordResponse":
        return cls(
            id=str(row.id),
            patient_user_id=str(row.patient_user_id),
            date_of_birth=row.date_of_birth,
            sex=row.sex,
            blood_type=row.blood_type,
            allergies=row.allergies,
            chronic_conditions=row.chronic_conditions,
            current_medications=row.current_medications,
            medical_notes=row.medical_notes,
            emergency_contact_name=row.emergency_contact_name,
            emergency_contact_phone=row.emergency_contact_phone,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
