from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime
from enum import Enum

class CloudProvider(str, Enum):
    """Enum para proveedores de nube"""
    GOOGLE_DRIVE = "google_drive"
    KEEPI_CLOUD = "keepi_cloud"  # S3

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

class CloudProviderInfo(BaseModel):
    """Información sobre proveedores de nube disponibles"""
    provider: CloudProvider
    name: str
    description: str
    features: list[str]
    storage_limit: Optional[str] = None
    is_available: bool = True
