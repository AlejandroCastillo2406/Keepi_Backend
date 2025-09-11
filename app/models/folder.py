from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime

class FolderBase(BaseModel):
    """Modelo base para carpeta"""
    name: str
    category: str
    description: Optional[str] = None
    parent_folder_id: Optional[str] = None

class FolderCreate(FolderBase):
    """Modelo para crear carpeta"""
    drive_folder_id: str
    drive_parent_id: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None

class FolderUpdate(BaseModel):
    """Modelo para actualizar carpeta"""
    name: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    parent_folder_id: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    is_archived: Optional[bool] = None
    is_favorite: Optional[bool] = None

class FolderResponse(FolderBase):
    """Modelo de respuesta para carpeta"""
    id: str
    user_id: str
    drive_folder_id: str
    drive_parent_id: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    documents_count: int = 0
    subfolders_count: int = 0
    is_archived: bool = False
    is_favorite: bool = False
    created_at: datetime
    updated_at: datetime

class FolderStructure(BaseModel):
    """Modelo para estructura de carpetas"""
    id: str
    name: str
    category: str
    drive_folder_id: str
    documents_count: int
    subfolders: List['FolderStructure'] = []
    created_at: datetime
    updated_at: datetime

# Para referencias circulares
FolderStructure.model_rebuild()
