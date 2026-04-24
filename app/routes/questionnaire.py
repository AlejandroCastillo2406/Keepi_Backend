"""Rutas del módulo de cuestionarios de salud (solo doctor)."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_doctor_user
from app.models.questionnaire import (
    OverridesRequest,
    QuestionCreateRequest,
    QuestionResponse,
    QuestionUpdateRequest,
    SpecialtySummary,
    TemplateCreateRequest,
    TemplateDetailResponse,
    TemplateQuestionsUpsertRequest,
    TemplateResponse,
    TemplateUpdateRequest,
    ToggleRequest,
)
from app.models.questionnaire_invitation import (
    PublicInvitationSubmitRequest,
    PublicInvitationSubmitResponse,
    PublicInvitationViewResponse,
    QuestionnaireInvitationSendResponse,
    QuestionnaireInvitationSummaryResponse,
    QuestionnaireSendInvitationRequest,
    QuestionnaireInvitation,
    QuestionnaireInvitationItem,
    QuestionnaireInvitationAnswer,
)
from app.models.user import User
from app.repositories.questionnaire_repository import QuestionnaireRepository
from app.services.notificaciones.questionnaire_invite_email_service import (
    build_public_questionnaire_link,
    send_questionnaire_invite_email,
)
from app.services.notificaciones.user_notify import notify_user_push_and_db

router = APIRouter()
logger = logging.getLogger(__name__)


StatusFilter = Literal["all", "active", "inactive"]


class PatientResponseItemView(BaseModel):
    question_text: str
    answer_value: Any
    answered_at: datetime


def _get_repo(db: Session = Depends(get_db)) -> QuestionnaireRepository:
    return QuestionnaireRepository(db)


def _parse_uuid(value: str, field: str = "id") -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"{field} inválido") from exc


# ──────────────── Specialties ────────────────


@router.get("/specialties", response_model=List[SpecialtySummary])
def list_specialties(
    current_user: User = Depends(require_doctor_user),
    repo: QuestionnaireRepository = Depends(_get_repo),
):
    return repo.list_specialties_with_counts(current_user.id)


@router.get(
    "/specialties/{specialty_id}/questions",
    response_model=List[QuestionResponse],
)
def list_specialty_questions(
    specialty_id: str,
    status: StatusFilter = Query("all"),
    current_user: User = Depends(require_doctor_user),
    repo: QuestionnaireRepository = Depends(_get_repo),
):
    spec_uuid = _parse_uuid(specialty_id, "specialty_id")
    repo.get_specialty(spec_uuid)
    return repo.list_questions(
        current_user.id,
        specialty_id=spec_uuid,
        status_filter=status,
    )


# ──────────────── Globals (specialty_id IS NULL) ────────────────


@router.get("/questions/globals", response_model=List[QuestionResponse])
def list_global_questions(
    status: StatusFilter = Query("all"),
    current_user: User = Depends(require_doctor_user),
    repo: QuestionnaireRepository = Depends(_get_repo),
):
    return repo.list_questions(
        current_user.id,
        only_globals=True,
        status_filter=status,
    )


# ──────────────── Question CRUD (custom) ────────────────


@router.post(
    "/questions",
    response_model=QuestionResponse,
    status_code=http_status.HTTP_201_CREATED,
)
def create_question(
    payload: QuestionCreateRequest,
    current_user: User = Depends(require_doctor_user),
    repo: QuestionnaireRepository = Depends(_get_repo),
):
    return repo.create_custom_question(current_user.id, payload)


@router.get("/questions/{question_id}", response_model=QuestionResponse)
def get_question(
    question_id: str,
    current_user: User = Depends(require_doctor_user),
    repo: QuestionnaireRepository = Depends(_get_repo),
):
    return repo.get_question_dto(current_user.id, _parse_uuid(question_id, "question_id"))


@router.patch("/questions/{question_id}", response_model=QuestionResponse)
def update_question(
    question_id: str,
    payload: QuestionUpdateRequest,
    current_user: User = Depends(require_doctor_user),
    repo: QuestionnaireRepository = Depends(_get_repo),
):
    return repo.update_custom_question(
        current_user.id, _parse_uuid(question_id, "question_id"), payload
    )


@router.delete("/questions/{question_id}", status_code=http_status.HTTP_204_NO_CONTENT)
def delete_question(
    question_id: str,
    current_user: User = Depends(require_doctor_user),
    repo: QuestionnaireRepository = Depends(_get_repo),
):
    repo.delete_custom_question(current_user.id, _parse_uuid(question_id, "question_id"))
    return None


@router.patch("/questions/{question_id}/toggle", response_model=QuestionResponse)
def toggle_question(
    question_id: str,
    payload: ToggleRequest,
    current_user: User = Depends(require_doctor_user),
    repo: QuestionnaireRepository = Depends(_get_repo),
):
    return repo.set_toggle(
        current_user.id, _parse_uuid(question_id, "question_id"), payload.is_active
    )


@router.patch("/questions/{question_id}/overrides", response_model=QuestionResponse)
def override_question(
    question_id: str,
    payload: OverridesRequest,
    current_user: User = Depends(require_doctor_user),
    repo: QuestionnaireRepository = Depends(_get_repo),
):
    return repo.set_overrides(
        current_user.id,
        _parse_uuid(question_id, "question_id"),
        is_required=payload.is_required,
        show_in_history=payload.show_in_history,
    )


# ──────────────── Templates ────────────────


@router.get("/templates", response_model=List[TemplateResponse])
def list_templates(
    current_user: User = Depends(require_doctor_user),
    repo: QuestionnaireRepository = Depends(_get_repo),
):
    return repo.list_templates(current_user.id)


@router.post(
    "/templates",
    response_model=TemplateDetailResponse,
    status_code=http_status.HTTP_201_CREATED,
)
def create_template(
    payload: TemplateCreateRequest,
    current_user: User = Depends(require_doctor_user),
    repo: QuestionnaireRepository = Depends(_get_repo),
):
    return repo.create_template(current_user.id, payload)


@router.get("/templates/{template_id}", response_model=TemplateDetailResponse)
def get_template(
    template_id: str,
    current_user: User = Depends(require_doctor_user),
    repo: QuestionnaireRepository = Depends(_get_repo),
):
    return repo.get_template(current_user.id, _parse_uuid(template_id, "template_id"))


@router.patch("/templates/{template_id}", response_model=TemplateDetailResponse)
def update_template(
    template_id: str,
    payload: TemplateUpdateRequest,
    current_user: User = Depends(require_doctor_user),
    repo: QuestionnaireRepository = Depends(_get_repo),
):
    return repo.update_template(
        current_user.id, _parse_uuid(template_id, "template_id"), payload
    )


@router.delete("/templates/{template_id}", status_code=http_status.HTTP_204_NO_CONTENT)
def delete_template(
    template_id: str,
    current_user: User = Depends(require_doctor_user),
    repo: QuestionnaireRepository = Depends(_get_repo),
):
    repo.delete_template(current_user.id, _parse_uuid(template_id, "template_id"))
    return None


@router.put(
    "/templates/{template_id}/questions",
    response_model=TemplateDetailResponse,
)
def upsert_template_questions(
    template_id: str,
    payload: TemplateQuestionsUpsertRequest,
    current_user: User = Depends(require_doctor_user),
    repo: QuestionnaireRepository = Depends(_get_repo),
):
    return repo.upsert_template_questions(
        current_user.id, _parse_uuid(template_id, "template_id"), payload
    )


# ──────────────── Invitations (doctor + public token) ────────────────


@router.post(
    "/invitations",
    response_model=QuestionnaireInvitationSendResponse,
    status_code=http_status.HTTP_201_CREATED,
)
def create_invitation(
    payload: QuestionnaireSendInvitationRequest,
    current_user: User = Depends(require_doctor_user),
    repo: QuestionnaireRepository = Depends(_get_repo),
):
    summary, raw_token = repo.create_invitation_batch(current_user.id, payload)
    public_link = build_public_questionnaire_link(raw_token)
    email_res = send_questionnaire_invite_email(
        to_email=summary.patient_email,
        patient_name=summary.patient_name,
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


@router.get(
    "/invitations/{invitation_id}",
    response_model=QuestionnaireInvitationSummaryResponse,
)
def get_invitation(
    invitation_id: str,
    current_user: User = Depends(require_doctor_user),
    repo: QuestionnaireRepository = Depends(_get_repo),
):
    return repo.get_invitation_summary(
        current_user.id,
        _parse_uuid(invitation_id, "invitation_id"),
    )


@router.get(
    "/public/{token}",
    response_model=PublicInvitationViewResponse,
)
def get_public_invitation(
    token: str,
    repo: QuestionnaireRepository = Depends(_get_repo),
):
    return repo.get_public_invitation_view(token)


@router.post(
    "/public/{token}/submit",
    response_model=PublicInvitationSubmitResponse,
)
def submit_public_invitation(
    token: str,
    payload: PublicInvitationSubmitRequest,
    repo: QuestionnaireRepository = Depends(_get_repo),
):
    response, invitation = repo.submit_public_invitation(token, payload)
    notify_user_push_and_db(
        repo._db,  # noqa: SLF001
        invitation.doctor_id,
        title="Cuestionario completado",
        message=f"{invitation.patient_name_snapshot} completó su cuestionario de salud.",
        notification_type="info",
        payload={
            "type": "questionnaire_completed",
            "invitation_id": str(invitation.id),
            "patient_id": str(invitation.patient_id),
        },
        push_data={
            "type": "questionnaire_completed",
            "invitation_id": str(invitation.id),
            "patient_id": str(invitation.patient_id),
        },
    )
    return response


# ──────────────── Respuestas del Paciente ────────────────

@router.get(
    "/patients/{patient_id}/responses",
    response_model=List[PatientResponseItemView],
)
def get_patient_questionnaire_responses(
    patient_id: str,
    current_user: User = Depends(require_doctor_user),
    db: Session = Depends(get_db),
):
    pat_uuid = _parse_uuid(patient_id, "patient_id")
    
    respuestas_db = (
        db.query(
            QuestionnaireInvitationItem.question_text_snapshot.label("question_text"),
            QuestionnaireInvitationAnswer.answer_json.label("answer_value"),
            QuestionnaireInvitationAnswer.answered_at
        )
        .select_from(QuestionnaireInvitation)
        .join(QuestionnaireInvitationItem, QuestionnaireInvitationItem.invitation_id == QuestionnaireInvitation.id)
        .join(QuestionnaireInvitationAnswer, QuestionnaireInvitationAnswer.invitation_item_id == QuestionnaireInvitationItem.id)
        .filter(QuestionnaireInvitation.patient_id == pat_uuid)
        .filter(QuestionnaireInvitation.doctor_id == current_user.id)
        .filter(QuestionnaireInvitation.status == "completed")
        .order_by(QuestionnaireInvitationAnswer.answered_at.desc())
        .all()
    )

    return [
        PatientResponseItemView(
            question_text=r.question_text,
            answer_value=r.answer_value,
            answered_at=r.answered_at
        )
        for r in respuestas_db
    ]