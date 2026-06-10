from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class ConsultationStatsDto(BaseModel):
    analysis_requested: int = 0
    analysis_uploaded: int = 0
    analysis_pending: int = 0
    timeline_events: int = 0


class ConsultationContextResponse(BaseModel):
    patient_name: Optional[str] = None
    patient_email: Optional[str] = None
    phone: Optional[str] = None
    sex: Optional[str] = None
    age_years: Optional[int] = None
    blood_type: Optional[str] = None
    weight_kg: Optional[float] = None
    allergies: Optional[str] = None
    has_clinical_intake: bool = False
    stats: ConsultationStatsDto = Field(default_factory=ConsultationStatsDto)


class ClinicalProfileUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=32)
    sex: Optional[str] = Field(None, max_length=32)
    age_years: Optional[int] = Field(None, ge=0, le=130)
    blood_type: Optional[str] = Field(None, max_length=16)
    weight_kg: Optional[float] = Field(None, ge=0, le=500)
    allergies: Optional[str] = Field(None, max_length=500)
