from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime
from enum import Enum

class ActionType(str, Enum):
    """Tipos de acciones auditables"""
    DOCUMENT_UPLOAD = "document_upload"
    DOCUMENT_DELETE = "document_delete"
    DOCUMENT_UPDATE = "document_update"
    FOLDER_CREATE = "folder_create"
    FOLDER_DELETE = "folder_delete"
    GOOGLE_DRIVE_CONNECT = "google_drive_connect"
    GOOGLE_DRIVE_DISCONNECT = "google_drive_disconnect"
    AI_ANALYSIS = "ai_analysis"
    USER_LOGIN = "user_login"
    USER_LOGOUT = "user_logout"
    SETTINGS_UPDATE = "settings_update"

class AuditLogBase(BaseModel):
    """Modelo base para log de auditoría"""
    user_id: str
    action_type: ActionType
    resource_type: str  # "document", "folder", "user", etc.
    resource_id: Optional[str] = None
    description: str
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None

class AuditLogCreate(AuditLogBase):
    """Modelo para crear log de auditoría"""
    metadata: Optional[Dict[str, Any]] = None
    success: bool = True
    error_message: Optional[str] = None

class AuditLogResponse(AuditLogBase):
    """Modelo de respuesta para log de auditoría"""
    id: str
    metadata: Optional[Dict[str, Any]] = None
    success: bool
    error_message: Optional[str] = None
    created_at: datetime

class AuditLogFilter(BaseModel):
    """Modelo para filtrar logs de auditoría"""
    user_id: Optional[str] = None
    action_type: Optional[ActionType] = None
    resource_type: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    success_only: Optional[bool] = None
    limit: int = 100
