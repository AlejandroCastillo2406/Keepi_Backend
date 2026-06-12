from typing import List, Optional

from pydantic import BaseModel

from app.dto.analysis_request_dto import AnalysisRequestResponse
from app.dto.consultation_context_dto import ConsultationContextResponse
from app.dto.timeline_dto import TimelineEventResponse


class ConsultationBootstrapResponse(BaseModel):
    context: ConsultationContextResponse
    timeline: List[TimelineEventResponse]
    analysis_requests: List[AnalysisRequestResponse]
    appointment_event: TimelineEventResponse
    doctor_note_content: Optional[str] = None
