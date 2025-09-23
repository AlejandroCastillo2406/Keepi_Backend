import uuid
from sqlalchemy import Column, String, DateTime, Boolean, JSON, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.config.database import Base
from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime
from enum import Enum

# Modelo SQLAlchemy para la tabla de configuración de usuario
class UserConfig(Base):
    __tablename__ = "user_configs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True, unique=True)
    cloud_provider = Column(String(50), nullable=False, default="google_drive")
    auto_categorization = Column(Boolean, default=True, nullable=False)
    aws_analysis_enabled = Column(Boolean, default=True, nullable=False)
    notification_preferences = Column(JSON, nullable=True, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relación con usuario
    user = relationship("User", back_populates="user_config")
    
    def __repr__(self):
        return f"<UserConfig(id={self.id}, user_id={self.user_id}, cloud_provider={self.cloud_provider})>"

# Enums para Pydantic
class CloudProvider(str, Enum):
    """Enum para proveedores de nube"""
    GOOGLE_DRIVE = "google_drive"
    KEEPI_CLOUD = "keepi_cloud"  # S3

# Modelos Pydantic para la API
class UserConfigBase(BaseModel):
    """Modelo base para configuración de usuario"""
    cloud_provider: CloudProvider = CloudProvider.GOOGLE_DRIVE
    auto_categorization: bool = True
    aws_analysis_enabled: bool = True
    notification_preferences: Optional[Dict[str, Any]] = None

class UserConfigCreate(UserConfigBase):
    """Modelo para crear configuración de usuario"""
    pass

class UserConfigUpdate(BaseModel):
    """Modelo para actualizar configuración de usuario"""
    cloud_provider: Optional[CloudProvider] = None
    auto_categorization: Optional[bool] = None
    aws_analysis_enabled: Optional[bool] = None
    notification_preferences: Optional[Dict[str, Any]] = None

class UserConfigResponse(UserConfigBase):
    """Modelo de respuesta para configuración de usuario"""
    id: str
    user_id: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class CloudProviderInfo(BaseModel):
    """Información sobre proveedores de nube disponibles"""
    provider: CloudProvider
    name: str
    description: str
    features: list[str]
    storage_limit: Optional[str] = None
    is_available: bool = True