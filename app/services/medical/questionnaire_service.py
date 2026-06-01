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
    DYNAMIC_QUESTIONNAIRE_MAX_QUESTIONS,
    PublicDynamicAnswerRequest,
    PublicDynamicAnswerResponse,
    PublicInvitationSubmitRequest,
    PublicInvitationSubmitResponse,
    PublicInvitationViewResponse,
    PublicPriorDocumentUploadResponse,
    QuestionnaireInvitation,
    QuestionnaireInvitationSendResponse,
    QuestionnaireInvitationSummaryResponse,
    QuestionnaireSendInvitationRequest,
)
from app.services.aws.bedrock_service import BedrockService
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
        self._bedrock = BedrockService()

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

    async def get_public_invitation_view(
        self, raw_token: str
    ) -> PublicInvitationViewResponse:
        view = self._repo.get_public_invitation_view(raw_token)
        if not view.is_dynamic or view.status != "pending" or view.questions:
            return view

        inv = self._repo._get_invitation_for_public_token(raw_token)
        if inv is None:
            return view
        inv = self._repo._mark_expired_if_needed(inv)
        if inv.status != "pending":
            return self._repo.get_public_invitation_view(raw_token)

        answered = self._repo.count_answered_dynamic_items(inv.id)
        if answered >= DYNAMIC_QUESTIONNAIRE_MAX_QUESTIONS:
            self._repo.complete_invitation(inv)
            return self._repo.get_public_invitation_view(raw_token)

        await self._generate_dynamic_question_item(inv, answered)
        return self._repo.get_public_invitation_view(raw_token)

    async def _generate_dynamic_question_item(
        self, invitation: QuestionnaireInvitation, answered_count: int
    ):
        conversation = self._repo.get_dynamic_conversation(invitation.id)
        spec = await self._bedrock.generate_dynamic_questionnaire_question(
            patient_name=invitation.patient_name_snapshot,
            conversation=conversation,
            question_number=answered_count + 1,
            max_questions=DYNAMIC_QUESTIONNAIRE_MAX_QUESTIONS,
        )
        return self._repo.add_dynamic_question_item(
            invitation.id,
            question_text=spec["question_text"],
            response_type=spec["response_type"],
            options=spec.get("options"),
            help_text=spec.get("help_text"),
            is_required=bool(spec.get("is_required", True)),
            sort_order=answered_count,
        )

    async def answer_dynamic_question(
        self, raw_token: str, payload: PublicDynamicAnswerRequest
    ) -> PublicDynamicAnswerResponse:
        inv = self._repo._get_invitation_for_public_token(raw_token)
        if inv is None:
            raise HTTPException(status_code=404, detail="Invitación no encontrada")
        if not bool(getattr(inv, "is_dynamic", False)):
            raise HTTPException(
                status_code=400,
                detail="Esta invitación no es un cuestionario dinámico",
            )
        inv = self._repo._mark_expired_if_needed(inv)
        if inv.status == "completed":
            raise HTTPException(
                status_code=409, detail="Este cuestionario ya fue completado"
            )
        if inv.status != "pending":
            raise HTTPException(status_code=400, detail="Invitación no disponible")

        pending = self._repo.get_pending_dynamic_item(inv.id)
        if pending is None:
            answered = self._repo.count_answered_dynamic_items(inv.id)
            if answered >= DYNAMIC_QUESTIONNAIRE_MAX_QUESTIONS:
                self._repo.complete_invitation(inv)
                return PublicDynamicAnswerResponse(
                    completed=True,
                    collect_prior_documents=bool(
                        getattr(inv, "collect_prior_documents", False)
                    ),
                    dynamic_answered_count=answered,
                )
            pending = await self._generate_dynamic_question_item(inv, answered)

        answer = payload.answer
        if pending.is_required_snapshot and answer in (None, "", [], {}):
            raise HTTPException(
                status_code=400, detail="Esta pregunta es obligatoria"
            )

        self._repo.save_dynamic_item_answer(pending, answer)
        answered = self._repo.count_answered_dynamic_items(inv.id)

        if answered >= DYNAMIC_QUESTIONNAIRE_MAX_QUESTIONS:
            self._repo.complete_invitation(inv)
            NotificationService(self._db).notify_questionnaire_completed_for_doctor(
                inv.doctor_id,
                patient_name=inv.patient_name_snapshot,
                invitation_id=str(inv.id),
                patient_id=str(inv.patient_id),
            )
            return PublicDynamicAnswerResponse(
                completed=True,
                collect_prior_documents=bool(
                    getattr(inv, "collect_prior_documents", False)
                ),
                dynamic_answered_count=answered,
            )

        next_item = await self._generate_dynamic_question_item(inv, answered)
        return PublicDynamicAnswerResponse(
            completed=False,
            collect_prior_documents=bool(
                getattr(inv, "collect_prior_documents", False)
            ),
            next_question=self._repo._invitation_item_to_view(next_item),
            dynamic_answered_count=answered,
        )

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

    def create_dynamic_invitation_with_email(
        self,
        doctor_id: uuid.UUID,
        patient_id: str,
        *,
        collect_prior_documents: bool = False,
    ) -> QuestionnaireInvitationSendResponse:
        payload = QuestionnaireSendInvitationRequest(
            patient_id=patient_id,
            collect_prior_documents=collect_prior_documents,
            use_dynamic_questionnaire=True,
        )
        return self.create_invitation_with_email(doctor_id, payload)

    def create_invitation_with_email(
        self,
        doctor_id: uuid.UUID,
        payload: QuestionnaireSendInvitationRequest,
    ) -> QuestionnaireInvitationSendResponse:
        summary, raw_token = self.create_invitation_batch(doctor_id, payload)
        public_link = build_public_questionnaire_link(raw_token)
        doctor = UserRepository(self._db).get_by_id_plain(doctor_id)
        doctor_name = (doctor.name if doctor else None) or "Tu médico"
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
            is_dynamic=bool(payload.use_dynamic_questionnaire),
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

    async def upload_public_prior_document(
        self, token: str, file: UploadFile
    ) -> PublicPriorDocumentUploadResponse:
        inv = self._repo._get_invitation_for_public_token(token)
        if not inv:
            raise HTTPException(status_code=404, detail="Invitación no encontrada")
        inv = self._repo._mark_expired_if_needed(inv)
        if not bool(getattr(inv, "collect_prior_documents", False)):
            raise HTTPException(
                status_code=403,
                detail="Esta invitación no permite subir documentos previos",
            )
        if inv.status != "completed":
            raise HTTPException(
                status_code=400,
                detail="Primero debes completar el cuestionario",
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
            description="Documento médico previo (cuestionario inicial)",
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
