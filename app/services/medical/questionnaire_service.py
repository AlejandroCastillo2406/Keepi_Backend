from __future__ import annotations

import io
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import HTTPException, UploadFile
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
from app.models.document import Document
from app.models.questionnaire_invitation import (
    PendingQuestionnaireInvitationView,
    DoctorInvitationQuestionsResponse,
    DoctorInvitationSubmitResponse,
    PublicInvitationSubmitRequest,
    PublicInvitationSubmitResponse,
    PublicIntakeSectionSubmitResponse,
    PublicInvitationViewResponse,
    PublicPriorDocumentUploadResponse,
    QuestionnaireInvitation,
    QuestionnaireInvitationSendResponse,
    QuestionnaireInvitationSummaryResponse,
    QuestionnaireSendInvitationRequest,
)
from app.repositories.document_repository import DocumentRepository
from app.services.almacenamiento import S3Service
from app.utils.doctor_patient_storage import (
    build_prior_document_filename,
    doctor_patient_prior_documents_folder,
)
from app.models.questionnaire import SpecialtySummary
from app.repositories.questionnaire_repository import QuestionnaireRepository
from app.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)
from app.services.notificaciones.notification_service import NotificationService
from app.services.medical.doctor_availability_service import DoctorAvailabilityService
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
                invitation_id=str(r.invitation_id) if r.invitation_id else None,
                questionnaire_name=(r.questionnaire_name or "").strip() or None,
                answered_by=(r.answered_by or "").strip() or None,
            )
            for r in rows
        ]

    def list_patient_pending_questionnaires(
        self, doctor_id: uuid.UUID, patient_id: uuid.UUID
    ) -> List[PendingQuestionnaireInvitationView]:
        return self._repo.list_patient_pending_questionnaire_invitations(
            patient_id, doctor_id
        )

    def get_invitation_questions_for_doctor(
        self, doctor_id: uuid.UUID, invitation_id: uuid.UUID
    ) -> DoctorInvitationQuestionsResponse:
        return self._repo.get_invitation_questions_for_doctor(
            doctor_id, invitation_id
        )

    def submit_doctor_invitation(
        self,
        doctor_id: uuid.UUID,
        invitation_id: uuid.UUID,
        payload: PublicInvitationSubmitRequest,
    ) -> DoctorInvitationSubmitResponse:
        return self._repo.submit_doctor_invitation(
            doctor_id, invitation_id, payload
        )

    def get_invitation_workflow_for_doctor(
        self, doctor_id: uuid.UUID, invitation_id: uuid.UUID
    ) -> PublicInvitationViewResponse:
        return self._repo.get_invitation_workflow_for_doctor(
            doctor_id, invitation_id
        )

    def save_doctor_intake_section(
        self,
        doctor_id: uuid.UUID,
        invitation_id: uuid.UUID,
        section_id: str,
        answers: dict,
    ) -> PublicIntakeSectionSubmitResponse:
        return self._repo.save_doctor_intake_section(
            doctor_id, invitation_id, section_id, answers
        )

    def finish_doctor_invitation(
        self, doctor_id: uuid.UUID, invitation_id: uuid.UUID
    ) -> dict:
        return self._repo.finish_doctor_invitation(doctor_id, invitation_id)

    async def upload_doctor_prior_document(
        self,
        doctor_id: uuid.UUID,
        invitation_id: uuid.UUID,
        file: UploadFile,
    ) -> PublicPriorDocumentUploadResponse:
        inv = self._repo._get_doctor_invitation(doctor_id, invitation_id)
        return await self._upload_prior_document_for_invitation(inv, file)

    def save_public_intake_section(
        self, raw_token: str, section_id: str, answers: dict
    ):
        response, completed_inv = self._repo.save_public_intake_section(
            raw_token, section_id, answers
        )
        if completed_inv is not None:
            NotificationService(self._db).notify_questionnaire_completed_for_doctor(
                completed_inv.doctor_id,
                patient_name=completed_inv.patient_name_snapshot,
                invitation_id=str(completed_inv.id),
                patient_id=str(completed_inv.patient_id),
            )
        return response

    def create_invitation_with_email(
        self,
        doctor_id: uuid.UUID,
        payload: QuestionnaireSendInvitationRequest,
    ) -> QuestionnaireInvitationSendResponse:
        summary, raw_token = self.create_invitation_batch(doctor_id, payload)
        public_link = build_public_questionnaire_link(raw_token)
        doctor = UserRepository(self._db).get_by_id_plain(doctor_id)
        doctor_name = (doctor.name if doctor else None) or "Tu médico"
        scheduling_link = DoctorAvailabilityService.resolve_patient_scheduling_link(
            self._db, uuid.UUID(str(summary.patient_id)), doctor_id
        )
        link_ok = (public_link or "").strip().startswith("http")
        if not link_ok:
            logger.warning(
                "Invitación %s: PUBLIC_QUESTIONNAIRE_BASE_URL vacía o inválida; "
                "el correo se enviará sin enlace web usable (link=%r).",
                summary.id,
                (public_link or "")[:80],
            )
        email_res = send_questionnaire_invite_email(
            to_email=summary.patient_email,
            patient_name=summary.patient_name,
            doctor_name=doctor_name,
            public_link=public_link,
            enable_clinical_intake=bool(
                getattr(payload, "enable_clinical_intake", False)
            ),
            intake_only=bool(getattr(payload, "intake_only", False)),
            collect_prior_documents=bool(
                getattr(payload, "collect_prior_documents", False)
            ),
            has_questionnaire=bool(
                getattr(payload, "template_ids", None) or []
                or getattr(payload, "question_ids", None) or []
            ),
            scheduling_link=scheduling_link,
        )
        if email_res.success:
            logger.info(
                "Invitación cuestionario %s: correo enviado a %s (ses_id=%s, link_web=%s).",
                summary.id,
                summary.patient_email,
                getattr(email_res, "ses_message_id", None),
                link_ok,
            )
        else:
            logger.warning(
                "Invitación cuestionario %s creada pero el correo NO se envió a %s: %s",
                summary.id,
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

    def complete_public_invitation_flow(self, token: str) -> QuestionnaireInvitation:
        inv = self._repo._get_invitation_for_public_token(token)
        inv = self._repo._mark_expired_if_needed(inv)
        already_completed = inv.status == "completed"
        inv = self._repo.complete_public_invitation(token)
        if not already_completed and inv.status == "completed":
            NotificationService(self._db).notify_questionnaire_completed_for_doctor(
                inv.doctor_id,
                patient_name=inv.patient_name_snapshot,
                invitation_id=str(inv.id),
                patient_id=str(inv.patient_id),
            )
        return inv

    async def upload_public_prior_document(
        self, token: str, file: UploadFile
    ) -> PublicPriorDocumentUploadResponse:
        inv = self._repo._get_invitation_for_public_token(token)
        if not inv:
            raise HTTPException(status_code=404, detail="Invitación no encontrada")
        inv = self._repo._mark_expired_if_needed(inv)
        return await self._upload_prior_document_for_invitation(inv, file)

    async def _upload_prior_document_for_invitation(
        self, inv: QuestionnaireInvitation, file: UploadFile
    ) -> PublicPriorDocumentUploadResponse:
        if not bool(getattr(inv, "collect_prior_documents", False)):
            raise HTTPException(
                status_code=403,
                detail="Esta invitación no permite subir documentos previos",
            )
        if inv.status not in ("pending", "completed"):
            raise HTTPException(status_code=400, detail="Invitación no disponible")
        enable_intake = bool(getattr(inv, "enable_clinical_intake", False))
        if enable_intake and not inv.intake_completed_at:
            raise HTTPException(
                status_code=400,
                detail="Primero debes completar la ficha clínica",
            )

        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="El archivo está vacío")

        mime = file.content_type or "application/octet-stream"
        original = (file.filename or "documento").strip()
        uploaded_at = datetime.now(timezone.utc)
        storage_name = build_prior_document_filename(
            uploaded_at,
            content_type=mime,
            original_filename=original,
            sequence=(uploaded_at.microsecond % 9000) + 1000,
        )
        patient_label = inv.patient_name_snapshot or "paciente"
        folder = f"{doctor_patient_prior_documents_folder(patient_label)}/"
        doctor_uid = str(inv.doctor_id)

        s3_service = S3Service()
        upload_res = await s3_service.upload_document(
            doctor_uid,
            io.BytesIO(content),
            storage_name,
            mime,
            folder=folder,
            storage_filename=storage_name,
        )
        s3_key = upload_res.get("file_path")
        file_url = upload_res.get("signed_url")
        category = doctor_patient_prior_documents_folder(patient_label)

        doc = Document(
            user_id=inv.doctor_id,
            name=storage_name,
            category=category,
            description="Documento médico previo (ficha clínica)",
            file_url=file_url,
            file_name=storage_name,
            file_size=len(content),
            file_type=mime.split("/")[0] if "/" in mime else mime,
            cloud_provider="keepi_cloud",
            drive_file_id=None,
            s3_key=s3_key,
            tags=[
                "documento_previo",
                f"patient:{inv.patient_id}",
                f"questionnaire_invitation:{inv.id}",
            ],
        )
        saved = DocumentRepository(self._db).persist(doc)

        return PublicPriorDocumentUploadResponse(
            message="Documento subido correctamente",
            document_id=str(saved.id),
            file_name=storage_name,
        )