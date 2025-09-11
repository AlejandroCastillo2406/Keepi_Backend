from pydantic import BaseModel, EmailStr
from typing import Optional, Dict, Any
from datetime import datetime

class UserBase(BaseModel):
    """Modelo base para usuario"""
    email: EmailStr
    name: str

class UserCreate(UserBase):
    """Modelo para crear usuario"""
    uid: str

class UserUpdate(BaseModel):
    """Modelo para actualizar usuario"""
    name: Optional[str] = None
    profile_picture: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None

class UserResponse(UserBase):
    """Modelo de respuesta para usuario"""
    uid: str
    profile_picture: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime

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
