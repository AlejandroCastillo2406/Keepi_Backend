import uuid
from sqlalchemy import Column, String, DateTime, Text, Boolean, JSON, Integer, Float, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.config.database import Base
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime

# Modelo SQLAlchemy para la tabla de análisis de AI
class AIAnalysis(Base):
    __tablename__ = "ai_analyses"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False, index=True)
    suggested_category = Column(String(100), nullable=False)
    confidence_score = Column(Float, nullable=False)
    extracted_text = Column(Text, nullable=True)
    analysis_metadata = Column(JSON, nullable=True, default=dict)
    tags = Column(ARRAY(String), nullable=True, default=list)
    expiry_date = Column(String(50), nullable=True)
    document_number = Column(String(100), nullable=True)
    organization = Column(String(255), nullable=True)
    processing_time_ms = Column(Integer, nullable=True)
    ai_model_version = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relaciones
    user = relationship("User", back_populates="ai_analyses")
    document = relationship("Document", back_populates="ai_analyses")
    
    def __repr__(self):
        return f"<AIAnalysis(id={self.id}, document_id={self.document_id}, category={self.suggested_category})>"

# Modelo SQLAlchemy para historial de análisis
class AIAnalysisHistory(Base):
    __tablename__ = "ai_analysis_history"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    analysis_version = Column(Integer, nullable=False)
    previous_category = Column(String(100), nullable=True)
    new_category = Column(String(100), nullable=False)
    confidence_score = Column(Float, nullable=False)
    reason_for_change = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Relaciones
    user = relationship("User")
    document = relationship("Document")
    
    def __repr__(self):
        return f"<AIAnalysisHistory(id={self.id}, document_id={self.document_id}, version={self.analysis_version})>"

# Modelos Pydantic para la API
class AIAnalysisBase(BaseModel):
    """Modelo base para análisis de AI"""
    document_id: str
    suggested_category: str
    confidence_score: float
    extracted_text: Optional[str] = None

class AIAnalysisCreate(AIAnalysisBase):
    """Modelo para crear análisis de AI"""
    analysis_metadata: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None
    expiry_date: Optional[str] = None
    document_number: Optional[str] = None
    organization: Optional[str] = None
    processing_time_ms: Optional[int] = None
    ai_model_version: Optional[str] = None

class AIAnalysisUpdate(BaseModel):
    """Modelo para actualizar análisis de AI"""
    suggested_category: Optional[str] = None
    confidence_score: Optional[float] = None
    analysis_metadata: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None
    expiry_date: Optional[str] = None
    document_number: Optional[str] = None
    organization: Optional[str] = None

class AIAnalysisResponse(AIAnalysisBase):
    """Modelo de respuesta para análisis de AI"""
    id: str
    user_id: str
    analysis_metadata: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None
    expiry_date: Optional[str] = None
    document_number: Optional[str] = None
    organization: Optional[str] = None
    processing_time_ms: Optional[int] = None
    ai_model_version: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True
    
    @classmethod
    def from_orm(cls, obj):
        """Convertir desde ORM asegurando que los UUIDs sean strings"""
        data = {
            "id": str(obj.id),
            "user_id": str(obj.user_id),
            "document_id": str(obj.document_id),
            "suggested_category": obj.suggested_category,
            "confidence_score": obj.confidence_score,
            "extracted_text": obj.extracted_text,
            "analysis_metadata": obj.analysis_metadata,
            "tags": obj.tags,
            "expiry_date": obj.expiry_date,
            "document_number": obj.document_number,
            "organization": obj.organization,
            "processing_time_ms": obj.processing_time_ms,
            "ai_model_version": obj.ai_model_version,
            "created_at": obj.created_at,
            "updated_at": obj.updated_at
        }
        return cls(**data)

class AIAnalysisHistoryResponse(BaseModel):
    """Modelo de respuesta para historial de análisis"""
    id: str
    document_id: str
    user_id: str
    analysis_version: int
    previous_category: Optional[str] = None
    new_category: str
    confidence_score: float
    reason_for_change: Optional[str] = None
    created_at: datetime
    
    class Config:
        from_attributes = True