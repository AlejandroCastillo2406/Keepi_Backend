import uuid
from sqlalchemy import Column, String, DateTime, Boolean, Text, Float, JSON, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.config.database import Base
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

# Modelo SQLAlchemy para la tabla de respaldos y sincronización
class BackupSync(Base):
    __tablename__ = "backup_syncs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    sync_type = Column(String(50), nullable=False)  # "backup", "sync", "restore"
    status = Column(String(20), nullable=False, default="pending")
    description = Column(Text, nullable=False)
    source_paths = Column(ARRAY(String), nullable=True)
    destination_folder_id = Column(String(255), nullable=True)
    include_deleted = Column(Boolean, default=False, nullable=False)
    compression = Column(Boolean, default=True, nullable=False)
    encryption = Column(Boolean, default=False, nullable=False)
    progress_percentage = Column(Float, default=0.0, nullable=False)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relación con usuario
    user = relationship("User")
    
    def __repr__(self):
        return f"<BackupSync(id={self.id}, user_id={self.user_id}, type={self.sync_type})>"

# Modelo SQLAlchemy para conflictos de sincronización
class SyncConflict(Base):
    __tablename__ = "sync_conflicts"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    backup_sync_id = Column(UUID(as_uuid=True), ForeignKey("backup_syncs.id"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    file_path = Column(String(500), nullable=False)
    conflict_type = Column(String(50), nullable=False)  # "modified", "deleted", "renamed"
    local_version = Column(JSON, nullable=True)
    remote_version = Column(JSON, nullable=True)
    resolution = Column(String(50), nullable=True)  # "keep_local", "keep_remote", "merge"
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Relaciones
    backup_sync = relationship("BackupSync")
    user = relationship("User")
    
    def __repr__(self):
        return f"<SyncConflict(id={self.id}, file_path={self.file_path}, type={self.conflict_type})>"

# Enums para Pydantic
class SyncStatus(str, Enum):
    """Estados de sincronización"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"

class BackupType(str, Enum):
    """Tipos de respaldo"""
    FULL = "full"
    INCREMENTAL = "incremental"
    SELECTIVE = "selective"

# Modelos Pydantic para la API
class BackupSyncBase(BaseModel):
    """Modelo base para respaldo y sincronización"""
    user_id: str
    sync_type: str  # "backup", "sync", "restore"
    status: SyncStatus
    description: str

class BackupSyncCreate(BackupSyncBase):
    """Modelo para crear respaldo/sincronización"""
    source_paths: Optional[List[str]] = None
    destination_folder_id: Optional[str] = None
    include_deleted: bool = False
    compression: bool = True
    encryption: bool = False

class BackupSyncUpdate(BaseModel):
    """Modelo para actualizar respaldo/sincronización"""
    status: Optional[SyncStatus] = None
    progress_percentage: Optional[float] = None
    error_message: Optional[str] = None
    completed_at: Optional[datetime] = None

class BackupSyncResponse(BackupSyncBase):
    """Modelo de respuesta para respaldo/sincronización"""
    id: str
    source_paths: Optional[List[str]] = None
    destination_folder_id: Optional[str] = None
    include_deleted: bool
    compression: bool
    encryption: bool
    progress_percentage: float = 0.0
    error_message: Optional[str] = None
    started_at: datetime
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class SyncConflictResponse(BaseModel):
    """Modelo de respuesta para conflictos de sincronización"""
    id: str
    backup_sync_id: str
    user_id: str
    file_path: str
    conflict_type: str  # "modified", "deleted", "renamed"
    local_version: Optional[Dict[str, Any]] = None
    remote_version: Optional[Dict[str, Any]] = None
    resolution: Optional[str] = None  # "keep_local", "keep_remote", "merge"
    created_at: datetime
    resolved_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True