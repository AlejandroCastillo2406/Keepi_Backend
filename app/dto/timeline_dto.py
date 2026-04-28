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

    class Config:
        from_attributes = True
