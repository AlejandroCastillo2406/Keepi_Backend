from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class ClinicalIntakeFieldDetail(BaseModel):
    key: str
    label: str
    value: str = ""


class ClinicalIntakeSectionDetail(BaseModel):
    id: str
    title: str
    subtitle: Optional[str] = None
    fields: List[ClinicalIntakeFieldDetail] = Field(default_factory=list)


class ClinicalIntakeDetailResponse(BaseModel):
    invitation_id: str
    patient_id: str
    completed_at: Optional[datetime] = None
    sections: List[ClinicalIntakeSectionDetail] = Field(default_factory=list)
