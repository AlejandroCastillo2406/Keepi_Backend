from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

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

class SyncConflict(BaseModel):
    """Modelo para conflictos de sincronización"""
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
