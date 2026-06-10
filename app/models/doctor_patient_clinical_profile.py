import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.core.database import Base


class DoctorPatientClinicalProfile(Base):
    """Datos clínicos del paciente que el médico puede completar manualmente."""

    __tablename__ = "doctor_patient_clinical_profiles"
    __table_args__ = (
        UniqueConstraint("doctor_id", "patient_id", name="uq_doctor_patient_clinical"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
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
    phone = Column(String(32), nullable=True)
    sex = Column(String(32), nullable=True)
    age_years = Column(Integer, nullable=True)
    blood_type = Column(String(16), nullable=True)
    weight_kg = Column(Float, nullable=True)
    allergies = Column(String(500), nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
