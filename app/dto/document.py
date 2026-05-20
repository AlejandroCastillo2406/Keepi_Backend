from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class DocumentBase(BaseModel):
    name: str
    category: str
    description: Optional[str] = None


class DocumentCreate(DocumentBase):
    file_url: Optional[str] = None
    file_name: Optional[str] = None
    file_size: Optional[int] = None
    file_type: Optional[str] = None
    expiry_date: Optional[datetime] = None
    document_metadata: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None
    drive_file_id: Optional[str] = None
    drive_folder_id: Optional[str] = None
    cloud_provider: Optional[str] = None
    s3_key: Optional[str] = None
    extracted_text: Optional[str] = None
    ai_analysis: Optional[Dict[str, Any]] = None


class DocumentUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    file_url: Optional[str] = None
    file_name: Optional[str] = None
    file_size: Optional[int] = None
    file_type: Optional[str] = None
    expiry_date: Optional[datetime] = None
    document_metadata: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None
    ai_analysis: Optional[Dict[str, Any]] = None
    is_archived: Optional[bool] = None
    is_favorite: Optional[bool] = None


class DocumentResponse(DocumentBase):
    id: str
    user_id: str
    file_url: Optional[str] = None
    file_name: Optional[str] = None
    file_size: Optional[int] = None
    file_type: Optional[str] = None
    expiry_date: Optional[datetime] = None
    document_metadata: Optional[Dict[str, Any]] = None
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

    class Config:
        from_attributes = True

    @classmethod
    def from_orm(cls, obj: Any) -> "DocumentResponse":
        return cls(
            id=str(obj.id),
            user_id=str(obj.user_id),
            name=obj.name,
            category=obj.category,
            description=obj.description,
            file_url=obj.file_url,
            file_name=obj.file_name,
            file_size=obj.file_size,
            file_type=obj.file_type,
            expiry_date=obj.expiry_date,
            document_metadata=obj.document_metadata,
            tags=obj.tags,
            drive_file_id=obj.drive_file_id,
            drive_folder_id=obj.folder.drive_folder_id if obj.folder else None,
            cloud_provider=obj.cloud_provider,
            s3_key=obj.s3_key,
            extracted_text=obj.extracted_text,
            ai_analysis=obj.ai_analysis,
            is_archived=obj.is_archived,
            is_favorite=obj.is_favorite,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )


class DocumentMetadata(BaseModel):
    tipo: Optional[str] = None
    numero: Optional[str] = None
    aseguradora: Optional[str] = None
    servicio: Optional[str] = None
    mes: Optional[str] = None
