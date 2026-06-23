from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.dto.analysis_request_dto import AnalysisRequestResponse
from app.dto.consultation_context_dto import ConsultationStatsDto
from app.dto.patient_profile_bootstrap_dto import PatientProfileBootstrapResponse
from app.repositories.analysis_request_repository import AnalysisRequestRepository
from app.services.medical.appointment_service import AppointmentService
from app.services.medical.consultation_context_service import ConsultationContextService
from app.services.medical.patient_timeline_service import PatientTimelineService
from app.services.medical.questionnaire_service import QuestionnaireService


class PatientProfileBootstrapService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_bootstrap(
        self, doctor_id: uuid.UUID, patient_id: uuid.UUID
    ) -> PatientProfileBootstrapResponse:
        # Single timeline fetch — reused for stats to avoid double query
        timeline_svc = PatientTimelineService(self._db)
        timeline = timeline_svc.timeline_for_doctor_patient(doctor_id, patient_id)

        analysis_rows = AnalysisRequestRepository(self._db).get_all_by_patient(
            patient_id
        )
        analysis = [
            AnalysisRequestResponse.model_validate(row) for row in analysis_rows
        ]

        uploaded = sum(
            1 for r in analysis_rows
            if r.status == "completed" and r.document_id is not None
        )
        pending = sum(
            1 for r in analysis_rows
            if r.status == "pending" and r.document_id is None
        )
        attendance = AppointmentService.compute_attendance_stats(
            self._db, doctor_id, patient_id
        )
        stats = ConsultationStatsDto(
            analysis_requested=len(analysis_rows),
            analysis_uploaded=uploaded,
            analysis_pending=pending,
            timeline_events=len(timeline),
            **attendance,
        )

        context_svc = ConsultationContextService(self._db)
        context = context_svc.get_context(doctor_id, patient_id, stats=stats)

        q_svc = QuestionnaireService(self._db)
        questionnaire = q_svc.list_patient_questionnaire_answers(doctor_id, patient_id)
        questionnaire_pending = q_svc.list_patient_pending_questionnaires(doctor_id, patient_id)

        return PatientProfileBootstrapResponse(
            context=context,
            timeline=timeline,
            analysis_requests=analysis,
            questionnaire_responses=questionnaire,
            questionnaire_pending=questionnaire_pending,
        )
