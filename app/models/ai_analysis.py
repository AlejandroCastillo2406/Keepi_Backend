from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime

class AIAnalysisBase(BaseModel):
    """Modelo base para análisis de AI"""
    document_id: str
    suggested_category: str
    confidence_score: float
    extracted_text: Optional[str] = None

class AIAnalysisCreate(AIAnalysisBase):
    """Modelo para crear análisis de AI"""
    metadata: Optional[Dict[str, Any]] = None
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
    metadata: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None
    expiry_date: Optional[str] = None
    document_number: Optional[str] = None
    organization: Optional[str] = None

class AIAnalysisResponse(AIAnalysisBase):
    """Modelo de respuesta para análisis de AI"""
    id: str
    user_id: str
    metadata: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None
    expiry_date: Optional[str] = None
    document_number: Optional[str] = None
    organization: Optional[str] = None
    processing_time_ms: Optional[int] = None
    ai_model_version: Optional[str] = None
    created_at: datetime
    updated_at: datetime

class AIAnalysisHistory(BaseModel):
    """Modelo para historial de análisis"""
    id: str
    document_id: str
    user_id: str
    analysis_version: int
    previous_category: Optional[str] = None
    new_category: str
    confidence_score: float
    reason_for_change: Optional[str] = None
    created_at: datetime
