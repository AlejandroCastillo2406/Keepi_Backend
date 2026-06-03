from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


class EventType(str, Enum):
    APPOINTMENT = "appointment"
    PRESCRIPTION = "prescription"
    ANALYSIS = "analysis"
    ANALYSIS_REQUEST = "analysis_request"
    ANALYSIS_UPLOAD = "analysis_upload"
    REGISTRATION = "registration"
    QUESTIONNAIRE = "questionnaire"
    CLINICAL_INTAKE = "clinical_intake"
    PRIOR_DOCUMENTS = "prior_documents"


class QuestionnaireStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    UNANSWERED = "unanswered"


class TimelineEventResponse(BaseModel):
    id: str
    date: str
    time: Optional[str] = None
    title: str
    actor: str
    event_type: EventType
    subtitle: Optional[str] = None
    description: str = ""
    occurred_at: str = Field(..., description="ISO-8601 para ordenar en cliente")
    visual_state: Literal["completed", "current", "future"] = "completed"

    questionnaire_status: Optional[QuestionnaireStatus] = None
    completed_at: Optional[str] = None
    action_patient_id: Optional[str] = Field(
        default=None,
        description="Paciente asociado (p. ej. abrir listado de documentos previos).",
    )
    prior_documents_count: Optional[int] = None
    has_doctor_note: bool = False
    doctor_note_preview: Optional[str] = Field(
        default=None,
        description="Vista previa de la nota clínica del médico (solo en vista doctor).",
    )

    class Config:
        from_attributes = True


class PriorDocumentItemResponse(BaseModel):
    id: str
    name: str
    file_name: Optional[str] = None
    s3_key: Optional[str] = None
    file_size: Optional[int] = None
    file_type: Optional[str] = None
    created_at: Optional[str] = None
