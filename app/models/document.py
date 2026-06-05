import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class DocumentStatus(str, Enum):
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class Document(Base):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    name = Column(String(255), nullable=False)
    category = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    file_url = Column(Text, nullable=True)
    file_name = Column(String(255), nullable=True)
    file_size = Column(Integer, nullable=True)
    file_type = Column(String(100), nullable=True)
    expiry_date = Column(DateTime(timezone=True), nullable=True)
    document_metadata = Column(JSON, nullable=True, default=dict)
    
    # Campo nuevo para el estado del flujo de trabajo
    status = Column(String(50), default=DocumentStatus.PENDING_REVIEW.value, nullable=False, index=True)
    
    tags = Column(ARRAY(String), nullable=True, default=list)
    drive_file_id = Column(String(255), nullable=True)
    cloud_provider = Column(String(50), nullable=True)
    s3_key = Column(String(500), nullable=True)
    extracted_text = Column(Text, nullable=True)
    ai_analysis = Column(JSON, nullable=True, default=dict)
    folder_id = Column(
        UUID(as_uuid=True), ForeignKey("folders.id"), nullable=True, index=True
    )
    is_archived = Column(Boolean, default=False, nullable=False)
    is_favorite = Column(Boolean, default=False, nullable=False)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user = relationship("User", back_populates="documents")
    folder = relationship("Folder", back_populates="documents")

    def __repr__(self):
        return f"<Document(id={self.id}, name={self.name}, status={self.status})>"


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
    folder_id: Optional[str] = None
    cloud_provider: Optional[str] = None
    s3_key: Optional[str] = None
    extracted_text: Optional[str] = None
    ai_analysis: Optional[Dict[str, Any]] = None
    status: Optional[DocumentStatus] = DocumentStatus.PENDING_REVIEW


class DocumentUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    file_url: Optional[str] = None
    file_name: Optional[str] = None
    s3_key: Optional[str] = None
    file_size: Optional[int] = None
    file_type: Optional[str] = None
    expiry_date: Optional[datetime] = None
    document_metadata: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None
    ai_analysis: Optional[Dict[str, Any]] = None
    is_archived: Optional[bool] = None
    is_favorite: Optional[bool] = None
    status: Optional[DocumentStatus] = None


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
    cloud_provider: Optional[str] = None
    s3_key: Optional[str] = None
    extracted_text: Optional[str] = None
    ai_analysis: Optional[Dict[str, Any]] = None
    status: DocumentStatus
    is_archived: bool = False
    is_favorite: bool = False
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

    @classmethod
    def from_orm(cls, obj):
        # Lógica defensiva para ai_analysis
        ai_analysis_data = obj.ai_analysis
        
        if isinstance(ai_analysis_data, list):
            # Si es una lista, tomamos el primer elemento (si existe) o un dict vacío
            ai_analysis_data = ai_analysis_data[0] if ai_analysis_data else {}
        elif not isinstance(ai_analysis_data, dict):
            # Si no es ni lista ni dict, devolvemos dict vacío
            ai_analysis_data = {}

        data = {
            "id": str(obj.id),
            "user_id": str(obj.user_id),
            "name": obj.name,
            "category": obj.category,
            "description": obj.description,
            "file_url": obj.file_url,
            "file_name": obj.file_name,
            "file_size": obj.file_size,
            "file_type": obj.file_type,
            "expiry_date": obj.expiry_date,
            "document_metadata": obj.document_metadata,
            "status": obj.status,
            "tags": obj.tags,
            "drive_file_id": obj.drive_file_id,
            "drive_folder_id": obj.folder.drive_folder_id if obj.folder else None,
            "cloud_provider": obj.cloud_provider,
            "s3_key": obj.s3_key,
            "extracted_text": obj.extracted_text,
            "ai_analysis": ai_analysis_data, # <--- Usamos el dato "limpiado"
            "is_archived": obj.is_archived,
            "is_favorite": obj.is_favorite,
            "created_at": obj.created_at,
            "updated_at": obj.updated_at,
        }
        return cls(**data)


class DocumentMetadata(BaseModel):
    tipo: Optional[str] = None
    numero: Optional[str] = None
    aseguradora: Optional[str] = None
    servicio: Optional[str] = None
    mes: Optional[str] = None