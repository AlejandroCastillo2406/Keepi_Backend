from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional


class AnalysisRequestCreate(BaseModel):
    patient_id: UUID
    description: str
    expires_at: Optional[datetime] = None


class AnalysisRequestResponse(BaseModel):
    id: UUID
    doctor_id: UUID
    patient_id: UUID
    description: str
    status: str
    created_at: datetime
    document_id: Optional[UUID] = None
    completed_at: Optional[datetime] = None

    class Config:

        from_attributes = True
