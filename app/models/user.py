import uuid
from sqlalchemy import Column, String, DateTime, Text, Boolean, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.config.database import Base
from pydantic import BaseModel, EmailStr
from typing import Optional, Dict, Any
from datetime import datetime

# Modelo SQLAlchemy para la tabla de usuarios
class User(Base):
    __tablename__ = "users"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=False)
    hashed_password = Column(String(255), nullable=True)  # Para autenticación local
    refresh_token = Column(String(500), nullable=True)  # Para refresh token
    profile_picture = Column(Text, nullable=True)
    settings = Column(JSON, nullable=True, default=dict)
    storage_preference = Column(String(50), nullable=True, default="local")
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relaciones
    documents = relationship("Document", back_populates="user")
    ai_analyses = relationship("AIAnalysis", back_populates="user")
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
    profile_picture: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None
    storage_preference: Optional[str] = "local"

class UserLogin(BaseModel):
    """Modelo para login de usuario"""
    email: EmailStr
    password: str

class UserUpdate(BaseModel):
    """Modelo para actualizar usuario"""
    name: Optional[str] = None
    profile_picture: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None
    storage_preference: Optional[str] = None
    is_active: Optional[bool] = None

class UserResponse(UserBase):
    """Modelo de respuesta para usuario"""
    id: str
    profile_picture: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None
    storage_preference: Optional[str] = None
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
            "profile_picture": obj.profile_picture,
            "settings": obj.settings,
            "storage_preference": obj.storage_preference,
            "is_active": obj.is_active,
            "created_at": obj.created_at,
            "updated_at": obj.updated_at
        }
        return cls(**data)

class UserSettings(BaseModel):
    """Modelo para configuración de usuario"""
    notifications_enabled: bool = True
    language: str = "es"
    theme: str = "light"
    storage_limit: Optional[int] = None
    auto_backup: bool = False
    backup_frequency: str = "weekly"
    ai_analysis_enabled: bool = True
    auto_categorization: bool = True
    drive_sync_enabled: bool = False
    sync_frequency: str = "daily"
    encryption_enabled: bool = False
    two_factor_auth: bool = False
    session_timeout_minutes: int = 60