import uuid
from sqlalchemy import Column, String, DateTime, Text, JSON, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, ARRAY, REAL
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.config.database import Base
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime

# Modelo SQLAlchemy para la tabla de índice de búsqueda
class SearchIndex(Base):
    __tablename__ = "search_indices"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    content = Column(Text, nullable=False)
    title = Column(String(255), nullable=False)
    category = Column(String(100), nullable=False)
    tags = Column(ARRAY(String), nullable=True, default=list)
    search_metadata = Column(JSON, nullable=True, default=dict)
    file_type = Column(String(100), nullable=True)
    language = Column(String(10), nullable=False, default="es")
    search_vector = Column(ARRAY(REAL), nullable=True)  # Para búsqueda vectorial
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relaciones
    document = relationship("Document")
    user = relationship("User")
    
    def __repr__(self):
        return f"<SearchIndex(id={self.id}, document_id={self.document_id}, title={self.title})>"

# Modelos Pydantic para la API
class SearchIndexBase(BaseModel):
    """Modelo base para índice de búsqueda"""
    document_id: str
    user_id: str
    content: str
    title: str
    category: str

class SearchIndexCreate(SearchIndexBase):
    """Modelo para crear índice de búsqueda"""
    tags: Optional[List[str]] = None
    search_metadata: Optional[Dict[str, Any]] = None
    file_type: Optional[str] = None
    language: str = "es"
    search_vector: Optional[List[float]] = None

class SearchIndexUpdate(BaseModel):
    """Modelo para actualizar índice de búsqueda"""
    content: Optional[str] = None
    title: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    search_metadata: Optional[Dict[str, Any]] = None
    search_vector: Optional[List[float]] = None

class SearchIndexResponse(SearchIndexBase):
    """Modelo de respuesta para índice de búsqueda"""
    id: str
    tags: Optional[List[str]] = None
    search_metadata: Optional[Dict[str, Any]] = None
    file_type: Optional[str] = None
    language: str
    search_vector: Optional[List[float]] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class SearchResult(BaseModel):
    """Modelo para resultado de búsqueda"""
    document_id: str
    title: str
    category: str
    relevance_score: float
    matched_terms: List[str]
    snippet: str
    file_type: Optional[str] = None
    created_at: datetime

class SearchQuery(BaseModel):
    """Modelo para consulta de búsqueda"""
    query: str
    category: Optional[str] = None
    file_type: Optional[str] = None
    tags: Optional[List[str]] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    limit: int = 20
    offset: int = 0