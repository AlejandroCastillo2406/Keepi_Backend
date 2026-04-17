from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional

class AnalysisRequestCreate(BaseModel):
    """
    DTO para la creación de una solicitud (lo que envía el Doctor).
    """
    patient_id: UUID
    description: str

class AnalysisRequestResponse(BaseModel):
    """
    DTO para la respuesta de la API (lo que reciben Flutter y el Dashboard).
    """
    id: UUID
    doctor_id: UUID
    patient_id: UUID
    description: str
    status: str
    created_at: datetime
    document_id: Optional[UUID] = None
    completed_at: Optional[datetime] = None

    class Config:
        # Esto permite que FastAPI convierta los modelos de SQLAlchemy 
        # (objetos de BD) a este DTO automáticamente.
        from_attributes = True