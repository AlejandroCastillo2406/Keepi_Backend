from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime

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
    metadata: Optional[Dict[str, Any]] = None
    file_type: Optional[str] = None
    language: str = "es"
    search_vector: Optional[List[float]] = None

class SearchIndexUpdate(BaseModel):
    """Modelo para actualizar índice de búsqueda"""
    content: Optional[str] = None
    title: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None
    search_vector: Optional[List[float]] = None

class SearchIndexResponse(SearchIndexBase):
    """Modelo de respuesta para índice de búsqueda"""
    id: str
    tags: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None
    file_type: Optional[str] = None
    language: str
    search_vector: Optional[List[float]] = None
    created_at: datetime
    updated_at: datetime

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
