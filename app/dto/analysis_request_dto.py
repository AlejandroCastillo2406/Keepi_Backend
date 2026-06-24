from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime
from typing import Any, Dict, List, Optional


class AnalysisRequestCreate(BaseModel):
    patient_id: UUID
    description: str
    expires_at: Optional[datetime] = None
    doctor_note: Optional[str] = Field(
        default=None,
        description="Nota clínica del médico vinculada al evento del timeline.",
    )


class AnalysisRequestResponse(BaseModel):
    id: UUID
    doctor_id: UUID
    patient_id: UUID
    description: str
    status: str
    created_at: datetime
    document_id: Optional[UUID] = None
    completed_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None

    class Config:

        from_attributes = True


def enrich_analysis_request_responses(
    rows: List[Any],
    expires_by_request_id: Dict[UUID, datetime],
) -> List[AnalysisRequestResponse]:
    out: List[AnalysisRequestResponse] = []
    for row in rows:
        resp = AnalysisRequestResponse.model_validate(row)
        exp = expires_by_request_id.get(row.id)
        if exp is not None:
            resp = resp.model_copy(update={"expires_at": exp})
        out.append(resp)
    return out
