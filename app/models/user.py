import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from typing import Optional
from datetime import datetime
from pydantic import BaseModel, EmailStr

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=False)
    hashed_password = Column(String(255), nullable=True)
    refresh_token = Column(String(500), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False, index=True)
    must_change_password = Column(Boolean, default=False, nullable=False)
    created_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    role = relationship("Role", lazy="joined")
    created_by = relationship(
        "User", remote_side=[id], foreign_keys=[created_by_user_id]
    )
    documents = relationship("Document", back_populates="user")
    user_config = relationship("UserConfig", back_populates="user", uselist=False)
    notifications = relationship("Notification", back_populates="user")
    folders = relationship("Folder", back_populates="user")
    oauth_credentials = relationship("OAuthCredentials", back_populates="user")
    subscription = relationship("Subscription", back_populates="user", uselist=False)

    def __repr__(self):
        return f"<User(id={self.id}, email={self.email}, name={self.name})>"


class UserBase(BaseModel):
    email: EmailStr
    name: str


class UserCreate(UserBase):

    password: Optional[str] = None
    role_name: Literal["USER", "DOCTOR"] = "USER"


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserUpdate(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None


class PasswordChangeRequest(BaseModel):

    current_password: str
    new_password: str = Field(..., min_length=8)


class DoctorCreatePatientRequest(BaseModel):

    email: EmailStr
    name: str
    is_first_consultation: bool = False

class DoctorCreatePatientResponse(BaseModel):
    id: str
    email: EmailStr
    name: str
    message: str = "Paciente creado correctamente."
    email_sent: bool = False
    email_error: Optional[str] = None


class UserResponse(UserBase):
    id: str
    is_active: bool = True
    role_id: int
    role_name: str
    must_change_password: bool = False
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

    @classmethod
    def from_orm(cls, obj):
        role_name = obj.role.name if getattr(obj, "role", None) is not None else ""
        data = {
            "id": str(obj.id),
            "email": obj.email,
            "name": obj.name,
            "is_active": obj.is_active,
            "role_id": obj.role_id,
            "role_name": role_name,
            "must_change_password": bool(obj.must_change_password),
            "created_at": obj.created_at,
            "updated_at": obj.updated_at,
        }
        return cls(**data)
    
class DoctorPatientListItemResponse(BaseModel):
    id: str
    email: EmailStr
    name: str
    is_active: bool
    created_at: datetime

    phone: Optional[str] = None
    sex: Optional[str] = None
    age_years: Optional[int] = None
    blood_type: Optional[str] = None
    weight_kg: Optional[float] = None
    allergies: Optional[str] = None

    appointments_total: int = 0
    appointments_attended: int = 0
    appointments_no_show: int = 0
    appointments_pending_attendance: int = 0

    last_appointment_date: Optional[datetime] = None
    next_appointment_date: Optional[datetime] = None

    documents_total: int = 0
    has_clinical_profile: bool = False
