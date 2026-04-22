import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, Field, model_validator
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base
from app.models.patient_medical_record import MedicalRecordInitialData, PatientMedicalRecord


# Modelo SQLAlchemy para la tabla de usuarios
class User(Base):
    __tablename__ = "users"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=False)
    hashed_password = Column(String(255), nullable=True)  # Para autenticación local
    refresh_token = Column(String(500), nullable=True)  # Para refresh token
    is_active = Column(Boolean, default=True, nullable=False)
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False, index=True)
    must_change_password = Column(Boolean, default=False, nullable=False)
    created_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    specialty_id = Column(
        UUID(as_uuid=True),
        ForeignKey("medical_specialties.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relaciones
    role = relationship("Role", lazy="joined")
    created_by = relationship("User", remote_side=[id], foreign_keys=[created_by_user_id])
    documents = relationship("Document", back_populates="user")
    user_config = relationship("UserConfig", back_populates="user", uselist=False)
    notifications = relationship("Notification", back_populates="user")
    folders = relationship("Folder", back_populates="user")
    oauth_credentials = relationship("OAuthCredentials", back_populates="user")
    subscription = relationship("Subscription", back_populates="user", uselist=False)
    medical_record = relationship(
        "PatientMedicalRecord",
        back_populates="patient",
        uselist=False,
        foreign_keys=[PatientMedicalRecord.patient_user_id],
    )
    specialty = relationship("MedicalSpecialty", foreign_keys=[specialty_id])

    def __repr__(self):
        return f"<User(id={self.id}, email={self.email}, name={self.name})>"

# Modelos Pydantic para la API
class UserBase(BaseModel):
    """Modelo base para usuario"""
    email: EmailStr
    name: str

class UserCreate(UserBase):
    """Modelo para crear usuario (autoregistro: solo USER o DOCTOR; PACIENTE lo crea un médico)."""

    password: Optional[str] = None
    role_name: Literal["USER", "DOCTOR"] = "USER"

class UserLogin(BaseModel):
    """Modelo para login de usuario"""
    email: EmailStr
    password: str

class UserUpdate(BaseModel):
    """Modelo para actualizar usuario"""
    name: Optional[str] = None
    is_active: Optional[bool] = None


class PasswordChangeRequest(BaseModel):
    """Cambio de contraseña (obligatorio si must_change_password)."""

    current_password: str
    new_password: str = Field(..., min_length=8)


class DoctorCreatePatientRequest(BaseModel):
    """Alta de paciente por médico + expediente inicial."""

    email: EmailStr
    name: str
    medical_record: MedicalRecordInitialData

    @model_validator(mode="before")
    @classmethod
    def _wrap_legacy_body(cls, data: object) -> object:
        if isinstance(data, dict) and "medical_record" not in data:
            return {**data, "medical_record": {}}
        return data

    @model_validator(mode="after")
    def _require_clinical_content(self) -> "DoctorCreatePatientRequest":
        data = self.medical_record.model_dump()
        has_value = False
        for v in data.values():
            if v is None:
                continue
            if isinstance(v, str) and not v.strip():
                continue
            has_value = True
            break
        if not has_value:
            raise ValueError("Completa al menos un campo del expediente médico")
        return self


class DoctorCreatePatientResponse(BaseModel):
    id: str
    email: EmailStr
    name: str
    message: str = "Paciente creado. Credenciales enviadas por correo."


class UserResponse(UserBase):
    """Modelo de respuesta para usuario"""
    id: str
    is_active: bool = True
    role_id: int
    role_name: str
    must_change_password: bool = False
    specialty_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

    @classmethod
    def from_orm(cls, obj):
        """Convertir desde ORM asegurando que el ID sea string"""
        role_name = obj.role.name if getattr(obj, "role", None) is not None else ""
        spec = getattr(obj, "specialty_id", None)
        data = {
            "id": str(obj.id),
            "email": obj.email,
            "name": obj.name,
            "is_active": obj.is_active,
            "role_id": obj.role_id,
            "role_name": role_name,
            "must_change_password": bool(obj.must_change_password),
            "specialty_id": str(spec) if spec is not None else None,
            "created_at": obj.created_at,
            "updated_at": obj.updated_at,
        }
        return cls(**data)