from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime

class DocumentBase(BaseModel):
    """Modelo base para documento"""
    name: str
    category: str
    description: Optional[str] = None

class DocumentCreate(DocumentBase):
    """Modelo para crear documento"""
    file_url: Optional[str] = None
    file_name: Optional[str] = None
    file_size: Optional[int] = None
    file_type: Optional[str] = None
    expiry_date: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None
    drive_file_id: Optional[str] = None
    drive_folder_id: Optional[str] = None
    cloud_provider: Optional[str] = None
    s3_key: Optional[str] = None
    extracted_text: Optional[str] = None
    ai_analysis: Optional[Dict[str, Any]] = None

class DocumentUpdate(BaseModel):
    """Modelo para actualizar documento"""
    name: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    file_url: Optional[str] = None
    file_name: Optional[str] = None
    file_size: Optional[int] = None
    file_type: Optional[str] = None
    expiry_date: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None
    is_archived: Optional[bool] = None
    is_favorite: Optional[bool] = None

class DocumentResponse(DocumentBase):
    """Modelo de respuesta para documento"""
    id: str
    user_id: str
    file_url: Optional[str] = None
    file_name: Optional[str] = None
    file_size: Optional[int] = None
    file_type: Optional[str] = None
    expiry_date: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None
    drive_file_id: Optional[str] = None
    drive_folder_id: Optional[str] = None
    cloud_provider: Optional[str] = None
    s3_key: Optional[str] = None
    extracted_text: Optional[str] = None
    ai_analysis: Optional[Dict[str, Any]] = None
    is_archived: bool = False
    is_favorite: bool = False
    created_at: datetime
    updated_at: datetime

class DocumentMetadata(BaseModel):
    """Modelo para metadatos de documento"""
    tipo: Optional[str] = None
    numero: Optional[str] = None
    aseguradora: Optional[str] = None
    servicio: Optional[str] = None
    mes: Optional[str] = None
