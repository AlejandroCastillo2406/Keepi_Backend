from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.dto.analysis_request_dto import AnalysisRequestResponse
from app.dto.patient_profile_bootstrap_dto import PatientProfileBootstrapResponse
from app.repositories.analysis_request_repository import AnalysisRequestRepository
from app.services.medical.consultation_bootstrap_service import ConsultationBootstrapService
from app.services.medical.consultation_context_service import ConsultationContextService
from app.services.medical.patient_timeline_service import PatientTimelineService
from app.services.medical.questionnaire_service import QuestionnaireService


class PatientProfileBootstrapService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_bootstrap(
        self, doctor_id: uuid.UUID, patient_id: uuid.UUID
    ) -> PatientProfileBootstrapResponse:
        timeline_svc = PatientTimelineService(self._db)
        timeline = timeline_svc.timeline_for_doctor_patient(doctor_id, patient_id)

        analysis_rows = AnalysisRequestRepository(self._db).get_all_by_patient(
            patient_id
        )
        analysis = [
            AnalysisRequestResponse.model_validate(row) for row in analysis_rows
        ]
        stats = ConsultationBootstrapService._stats_from(analysis_rows, len(timeline))

        context = ConsultationContextService(self._db).get_context(
            doctor_id, patient_id, stats=stats
        )
        questionnaire = QuestionnaireService(
            self._db
        ).list_patient_questionnaire_answers(doctor_id, patient_id)

        return PatientProfileBootstrapResponse(
            context=context,
            timeline=timeline,
            analysis_requests=analysis,
            questionnaire_responses=questionnaire,
        )
