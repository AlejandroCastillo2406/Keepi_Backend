import uuid
from sqlalchemy import Column, String, DateTime, Boolean, Text, JSON, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.config.database import Base
from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime
from enum import Enum

# Modelo SQLAlchemy para la tabla de logs de auditoría
class AuditLog(Base):
    __tablename__ = "audit_logs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    action_type = Column(String(50), nullable=False, index=True)
    resource_type = Column(String(50), nullable=False)
    resource_id = Column(String(255), nullable=True)
    description = Column(Text, nullable=False)
    ip_address = Column(String(45), nullable=True)  # IPv6 compatible
    user_agent = Column(Text, nullable=True)
    log_metadata = Column(JSON, nullable=True, default=dict)
    success = Column(Boolean, default=True, nullable=False)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Relación con usuario
    user = relationship("User", back_populates="audit_logs")
    
    def __repr__(self):
        return f"<AuditLog(id={self.id}, user_id={self.user_id}, action={self.action_type})>"

# Enums para Pydantic
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

# Modelos Pydantic para la API
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
    log_metadata: Optional[Dict[str, Any]] = None
    success: bool = True
    error_message: Optional[str] = None

class AuditLogResponse(AuditLogBase):
    """Modelo de respuesta para log de auditoría"""
    id: str
    log_metadata: Optional[Dict[str, Any]] = None
    success: bool
    error_message: Optional[str] = None
    created_at: datetime
    
    class Config:
        from_attributes = True

class AuditLogFilter(BaseModel):
    """Modelo para filtrar logs de auditoría"""
    user_id: Optional[str] = None
    action_type: Optional[ActionType] = None
    resource_type: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    success_only: Optional[bool] = None
    limit: int = 100