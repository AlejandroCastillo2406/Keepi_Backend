"""Expediente clínico del paciente (1:1 con usuario PACIENT)."""

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
        index=True,
    )
    birth_date = Column(Date, nullable=True)
    sex = Column(String(20), nullable=True)
    blood_type = Column(String(16), nullable=True)
    allergies = Column(Text, nullable=True)
    chronic_conditions = Column(Text, nullable=True)
    medications = Column(Text, nullable=True)
    surgical_history = Column(Text, nullable=True)
    family_history = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    emergency_contact_name = Column(String(255), nullable=True)
    emergency_contact_phone = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    patient = relationship("User", foreign_keys=[patient_user_id], back_populates="medical_record")


class MedicalRecordInitialData(BaseModel):
    """Datos del expediente al dar de alta al paciente (médico)."""

    birth_date: Optional[date] = None
    sex: Optional[str] = Field(None, max_length=20)
    blood_type: Optional[str] = Field(None, max_length=16)
    allergies: Optional[str] = None
    chronic_conditions: Optional[str] = None
    medications: Optional[str] = None
    surgical_history: Optional[str] = None
    family_history: Optional[str] = None
    notes: Optional[str] = None
    emergency_contact_name: Optional[str] = Field(None, max_length=255)
    emergency_contact_phone: Optional[str] = Field(None, max_length=64)


class MedicalRecordPatch(BaseModel):
    """Actualización parcial por el paciente (o futuro: médico autorizado)."""

    birth_date: Optional[date] = None
    sex: Optional[str] = Field(None, max_length=20)
    blood_type: Optional[str] = Field(None, max_length=16)
    allergies: Optional[str] = None
    chronic_conditions: Optional[str] = None
    medications: Optional[str] = None
    surgical_history: Optional[str] = None
    family_history: Optional[str] = None
    notes: Optional[str] = None
    emergency_contact_name: Optional[str] = Field(None, max_length=255)
    emergency_contact_phone: Optional[str] = Field(None, max_length=64)


class MedicalRecordResponse(BaseModel):
    id: str
    patient_user_id: str
    birth_date: Optional[date] = None
    sex: Optional[str] = None
    blood_type: Optional[str] = None
    allergies: Optional[str] = None
    chronic_conditions: Optional[str] = None
    medications: Optional[str] = None
    surgical_history: Optional[str] = None
    family_history: Optional[str] = None
    notes: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

    @classmethod
    def from_orm_record(cls, row: "PatientMedicalRecord") -> "MedicalRecordResponse":
        return cls(
            id=str(row.id),
            patient_user_id=str(row.patient_user_id),
            birth_date=row.birth_date,
            sex=row.sex,
            blood_type=row.blood_type,
            allergies=row.allergies,
            chronic_conditions=row.chronic_conditions,
            medications=row.medications,
            surgical_history=row.surgical_history,
            family_history=row.family_history,
            notes=row.notes,
            emergency_contact_name=row.emergency_contact_name,
            emergency_contact_phone=row.emergency_contact_phone,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
