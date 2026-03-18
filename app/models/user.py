import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr
from sqlalchemy import Boolean, Column, DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


# Modelo SQLAlchemy para la tabla de usuarios
class User(Base):
    __tablename__ = "users"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=False)
    hashed_password = Column(String(255), nullable=True)  # Para autenticación local
    refresh_token = Column(String(500), nullable=True)  # Para refresh token
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relaciones
    documents = relationship("Document", back_populates="user")
    user_config = relationship("UserConfig", back_populates="user", uselist=False)
    notifications = relationship("Notification", back_populates="user")
    folders = relationship("Folder", back_populates="user")
    oauth_credentials = relationship("OAuthCredentials", back_populates="user")
    subscription = relationship("Subscription", back_populates="user", uselist=False)
    
    def __repr__(self):
        return f"<User(id={self.id}, email={self.email}, name={self.name})>"

# Modelos Pydantic para la API
class UserBase(BaseModel):
    """Modelo base para usuario"""
    email: EmailStr
    name: str

class UserCreate(UserBase):
    """Modelo para crear usuario"""
    password: Optional[str] = None  # Para registro con contraseña

class UserLogin(BaseModel):
    """Modelo para login de usuario"""
    email: EmailStr
    password: str

class UserUpdate(BaseModel):
    """Modelo para actualizar usuario"""
    name: Optional[str] = None
    is_active: Optional[bool] = None

class UserResponse(UserBase):
    """Modelo de respuesta para usuario"""
    id: str
    is_active: bool = True
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

    @classmethod
    def from_orm(cls, obj):
        """Convertir desde ORM asegurando que el ID sea string"""
        data = {
            "id": str(obj.id),
            "email": obj.email,
            "name": obj.name,
            "is_active": obj.is_active,
            "created_at": obj.created_at,
            "updated_at": obj.updated_at
        }
        return cls(**data)