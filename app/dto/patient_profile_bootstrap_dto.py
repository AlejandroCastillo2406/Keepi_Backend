from typing import List

from pydantic import BaseModel

from app.dto.analysis_request_dto import AnalysisRequestResponse
from app.dto.consultation_context_dto import ConsultationContextResponse
from app.dto.questionnaire_responses_dto import PatientQuestionnaireAnswerView
from app.dto.timeline_dto import TimelineEventResponse


class PatientProfileBootstrapResponse(BaseModel):
    context: ConsultationContextResponse
    timeline: List[TimelineEventResponse]
    analysis_requests: List[AnalysisRequestResponse]
    questionnaire_responses: List[PatientQuestionnaireAnswerView]
