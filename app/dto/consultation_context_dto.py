from typing import Optional

from pydantic import BaseModel, Field


class ConsultationStatsDto(BaseModel):
    analysis_requested: int = 0
    analysis_uploaded: int = 0
    analysis_pending: int = 0
    timeline_events: int = 0


class ConsultationContextResponse(BaseModel):
    age_years: Optional[int] = None
    blood_type: Optional[str] = None
    weight_kg: Optional[float] = None
    allergies: Optional[str] = None
    has_clinical_intake: bool = False
    stats: ConsultationStatsDto = Field(default_factory=ConsultationStatsDto)


class ClinicalProfileUpdateRequest(BaseModel):
    age_years: Optional[int] = Field(None, ge=0, le=130)
    blood_type: Optional[str] = Field(None, max_length=16)
    weight_kg: Optional[float] = Field(None, ge=0, le=500)
    allergies: Optional[str] = Field(None, max_length=500)
