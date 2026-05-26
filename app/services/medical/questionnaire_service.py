from __future__ import annotations

import logging
import uuid
from typing import List, Optional

from sqlalchemy.orm import Session

from app.dto.questionnaire_responses_dto import PatientQuestionnaireAnswerView
from app.models.questionnaire import (
    QuestionCreateRequest,
    QuestionResponse,
    QuestionUpdateRequest,
    TemplateCreateRequest,
    TemplateDetailResponse,
    TemplateQuestionsUpsertRequest,
    TemplateResponse,
    TemplateUpdateRequest,
)
from app.models.questionnaire_invitation import (
    PublicInvitationSubmitRequest,
    PublicInvitationSubmitResponse,
    PublicInvitationViewResponse,
    QuestionnaireInvitation,
    QuestionnaireInvitationSendResponse,
    QuestionnaireInvitationSummaryResponse,
    QuestionnaireSendInvitationRequest,
)
from app.models.questionnaire import SpecialtySummary
from app.repositories.questionnaire_repository import QuestionnaireRepository
from app.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)
from app.services.notificaciones.notification_service import NotificationService
from app.services.notificaciones.questionnaire_invite_email_service import (
    build_public_questionnaire_link,
    send_questionnaire_invite_email,
)


class QuestionnaireService:
    def __init__(
        self,
        db: Session,
        questionnaire_repository: QuestionnaireRepository | None = None,
    ) -> None:
        self._db = db
        self._repo = questionnaire_repository or QuestionnaireRepository(db)

    def list_specialties_with_counts(
        self, doctor_id: uuid.UUID
    ) -> List[SpecialtySummary]:
        return self._repo.list_specialties_with_counts(doctor_id)

    def get_specialty(self, specialty_id: uuid.UUID):
        return self._repo.get_specialty(specialty_id)

    def list_questions(
        self,
        doctor_id: uuid.UUID,
        *,
        specialty_id: Optional[uuid.UUID] = None,
        only_globals: bool = False,
        status_filter: str = "all",
    ) -> List[QuestionResponse]:
        return self._repo.list_questions(
            doctor_id,
            specialty_id=specialty_id,
            only_globals=only_globals,
            status_filter=status_filter,
        )

    def create_custom_question(
        self, doctor_id: uuid.UUID, payload: QuestionCreateRequest
    ) -> QuestionResponse:
        return self._repo.create_custom_question(doctor_id, payload)

    def get_question_dto(
        self, doctor_id: uuid.UUID, question_id: uuid.UUID
    ) -> QuestionResponse:
        return self._repo.get_question_dto(doctor_id, question_id)

    def update_custom_question(
        self,
        doctor_id: uuid.UUID,
        question_id: uuid.UUID,
        payload: QuestionUpdateRequest,
    ) -> QuestionResponse:
        return self._repo.update_custom_question(doctor_id, question_id, payload)

    def delete_custom_question(
        self, doctor_id: uuid.UUID, question_id: uuid.UUID
    ) -> None:
        return self._repo.delete_custom_question(doctor_id, question_id)

    def set_toggle(
        self, doctor_id: uuid.UUID, question_id: uuid.UUID, is_active: bool
    ) -> QuestionResponse:
        return self._repo.set_toggle(doctor_id, question_id, is_active)

    def set_overrides(
        self,
        doctor_id: uuid.UUID,
        question_id: uuid.UUID,
        *,
        is_required: Optional[bool] = None,
        show_in_history: Optional[bool] = None,
    ) -> QuestionResponse:
        return self._repo.set_overrides(
            doctor_id,
            question_id,
            is_required=is_required,
            show_in_history=show_in_history,
        )

    def list_templates(self, doctor_id: uuid.UUID) -> List[TemplateResponse]:
        return self._repo.list_templates(doctor_id)

    def create_template(
        self, doctor_id: uuid.UUID, payload: TemplateCreateRequest
    ) -> TemplateDetailResponse:
        return self._repo.create_template(doctor_id, payload)

    def get_template(
        self, doctor_id: uuid.UUID, template_id: uuid.UUID
    ) -> TemplateDetailResponse:
        return self._repo.get_template(doctor_id, template_id)

    def update_template(
        self,
        doctor_id: uuid.UUID,
        template_id: uuid.UUID,
        payload: TemplateUpdateRequest,
    ) -> TemplateDetailResponse:
        return self._repo.update_template(doctor_id, template_id, payload)

    def delete_template(self, doctor_id: uuid.UUID, template_id: uuid.UUID) -> None:
        return self._repo.delete_template(doctor_id, template_id)

    def upsert_template_questions(
        self,
        doctor_id: uuid.UUID,
        template_id: uuid.UUID,
        payload: TemplateQuestionsUpsertRequest,
    ) -> TemplateDetailResponse:
        return self._repo.upsert_template_questions(doctor_id, template_id, payload)

    def create_invitation_batch(
        self, doctor_id: uuid.UUID, payload: QuestionnaireSendInvitationRequest
    ) -> tuple[QuestionnaireInvitationSummaryResponse, str]:
        return self._repo.create_invitation_batch(doctor_id, payload)

    def get_invitation_summary(
        self, doctor_id: uuid.UUID, invitation_id: uuid.UUID
    ) -> QuestionnaireInvitationSummaryResponse:
        return self._repo.get_invitation_summary(doctor_id, invitation_id)

    def get_public_invitation_view(
        self, raw_token: str
    ) -> PublicInvitationViewResponse:
        return self._repo.get_public_invitation_view(raw_token)

    def submit_public_invitation(
        self, raw_token: str, payload: PublicInvitationSubmitRequest
    ) -> tuple[PublicInvitationSubmitResponse, QuestionnaireInvitation]:
        return self._repo.submit_public_invitation(raw_token, payload)

    def list_patient_questionnaire_answers(
        self, doctor_id: uuid.UUID, patient_id: uuid.UUID
    ) -> List[PatientQuestionnaireAnswerView]:
        rows = self._repo.list_patient_completed_response_rows(patient_id, doctor_id)
        return [
            PatientQuestionnaireAnswerView(
                question_text=r.question_text,
                answer_value=r.answer_value,
                answered_at=r.answered_at,
            )
            for r in rows
        ]

    def create_invitation_with_email(
        self,
        doctor_id: uuid.UUID,
        payload: QuestionnaireSendInvitationRequest,
    ) -> QuestionnaireInvitationSendResponse:
        summary, raw_token = self.create_invitation_batch(doctor_id, payload)
        public_link = build_public_questionnaire_link(raw_token)
        doctor = UserRepository(self._db).get_by_id_plain(doctor_id)
        doctor_name = (doctor.name if doctor else None) or "Tu médico"
        email_res = send_questionnaire_invite_email(
            to_email=summary.patient_email,
            patient_name=summary.patient_name,
            doctor_name=doctor_name,
            public_link=public_link,
        )
        if not email_res.success:
            logger.warning(
                "Invitación cuestionario creada pero el correo no se envió: %s → %s",
                summary.patient_email,
                email_res.error,
            )
        return QuestionnaireInvitationSendResponse(
            invitation=summary,
            public_link=public_link,
            email_sent=bool(email_res.success),
            email_error=email_res.error,
        )

    def submit_public_invitation_with_notify(
        self,
        token: str,
        payload: PublicInvitationSubmitRequest,
    ) -> PublicInvitationSubmitResponse:
        response, invitation = self.submit_public_invitation(token, payload)
        NotificationService(self._db).notify_questionnaire_completed_for_doctor(
            invitation.doctor_id,
            patient_name=invitation.patient_name_snapshot,
            invitation_id=str(invitation.id),
            patient_id=str(invitation.patient_id),
        )
        return response
