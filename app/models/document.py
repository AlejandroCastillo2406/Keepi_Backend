import uuid
from sqlalchemy import Column, String, DateTime, Text, Boolean, JSON, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.config.database import Base
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime

# Modelo SQLAlchemy para la tabla de documentos
class Document(Base):
    __tablename__ = "documents"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    category = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    file_url = Column(Text, nullable=True)
    file_name = Column(String(255), nullable=True)
    file_size = Column(Integer, nullable=True)
    file_type = Column(String(100), nullable=True)
    expiry_date = Column(DateTime(timezone=True), nullable=True)
    document_metadata = Column(JSON, nullable=True, default=dict)
    tags = Column(ARRAY(String), nullable=True, default=list)
    drive_file_id = Column(String(255), nullable=True)
    drive_folder_id = Column(String(255), nullable=True)
    cloud_provider = Column(String(50), nullable=True)
    s3_key = Column(String(500), nullable=True)
    extracted_text = Column(Text, nullable=True)
    ai_analysis = Column(JSON, nullable=True, default=dict)
    folder_id = Column(UUID(as_uuid=True), ForeignKey("folders.id"), nullable=True, index=True)
    is_archived = Column(Boolean, default=False, nullable=False)
    is_favorite = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relaciones
    user = relationship("User", back_populates="documents")
    ai_analyses = relationship("AIAnalysis", back_populates="document")
    folder = relationship("Folder", back_populates="documents")
    
    def __repr__(self):
        return f"<Document(id={self.id}, name={self.name}, category={self.category})>"

# Modelos Pydantic para la API
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
    document_metadata: Optional[Dict[str, Any]] = None
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
    document_metadata: Optional[Dict[str, Any]] = None
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

class DocumentMetadata(BaseModel):
    """Modelo para metadatos de documento"""
    tipo: Optional[str] = None
    numero: Optional[str] = None
    aseguradora: Optional[str] = None
    servicio: Optional[str] = None
    mes: Optional[str] = None