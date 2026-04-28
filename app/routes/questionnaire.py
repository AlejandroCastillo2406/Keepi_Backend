from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import List, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from pydantic import BaseModel
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
from app.dto.questionnaire_responses_dto import PatientQuestionnaireAnswerView
from app.models.questionnaire_invitation import (
    PublicInvitationSubmitRequest,
    PublicInvitationSubmitResponse,
    PublicInvitationViewResponse,
    QuestionnaireInvitationSendResponse,
    QuestionnaireInvitationSummaryResponse,
    QuestionnaireSendInvitationRequest,
)
from app.models.user import User
from app.factories.medical_factory import get_questionnaire_service
from app.services.medical.questionnaire_service import QuestionnaireService

router = APIRouter()
logger = logging.getLogger(__name__)


StatusFilter = Literal["all", "active", "inactive"]


def _parse_uuid(value: str, field: str = "id") -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"{field} inválido") from exc


@router.get("/specialties", response_model=List[SpecialtySummary])
def list_specialties(
    current_user: User = Depends(require_doctor_user),
    svc: QuestionnaireService = Depends(get_questionnaire_service),
):
    return svc.list_specialties_with_counts(current_user.id)


@router.get(
    "/specialties/{specialty_id}/questions",
    response_model=List[QuestionResponse],
)
def list_specialty_questions(
    specialty_id: str,
    status: StatusFilter = Query("all"),
    current_user: User = Depends(require_doctor_user),
    svc: QuestionnaireService = Depends(get_questionnaire_service),
):
    spec_uuid = _parse_uuid(specialty_id, "specialty_id")
    svc.get_specialty(spec_uuid)
    return svc.list_questions(
        current_user.id,
        specialty_id=spec_uuid,
        status_filter=status,
    )


@router.get("/questions/globals", response_model=List[QuestionResponse])
def list_global_questions(
    status: StatusFilter = Query("all"),
    current_user: User = Depends(require_doctor_user),
    svc: QuestionnaireService = Depends(get_questionnaire_service),
):
    return svc.list_questions(
        current_user.id,
        only_globals=True,
        status_filter=status,
    )


@router.post(
    "/questions",
    response_model=QuestionResponse,
    status_code=http_status.HTTP_201_CREATED,
)
def create_question(
    payload: QuestionCreateRequest,
    current_user: User = Depends(require_doctor_user),
    svc: QuestionnaireService = Depends(get_questionnaire_service),
):
    return svc.create_custom_question(current_user.id, payload)


@router.get("/questions/{question_id}", response_model=QuestionResponse)
def get_question(
    question_id: str,
    current_user: User = Depends(require_doctor_user),
    svc: QuestionnaireService = Depends(get_questionnaire_service),
):
    return svc.get_question_dto(
        current_user.id, _parse_uuid(question_id, "question_id")
    )


@router.patch("/questions/{question_id}", response_model=QuestionResponse)
def update_question(
    question_id: str,
    payload: QuestionUpdateRequest,
    current_user: User = Depends(require_doctor_user),
    svc: QuestionnaireService = Depends(get_questionnaire_service),
):
    return svc.update_custom_question(
        current_user.id, _parse_uuid(question_id, "question_id"), payload
    )


@router.delete("/questions/{question_id}", status_code=http_status.HTTP_204_NO_CONTENT)
def delete_question(
    question_id: str,
    current_user: User = Depends(require_doctor_user),
    svc: QuestionnaireService = Depends(get_questionnaire_service),
):
    svc.delete_custom_question(current_user.id, _parse_uuid(question_id, "question_id"))
    return None


@router.patch("/questions/{question_id}/toggle", response_model=QuestionResponse)
def toggle_question(
    question_id: str,
    payload: ToggleRequest,
    current_user: User = Depends(require_doctor_user),
    svc: QuestionnaireService = Depends(get_questionnaire_service),
):
    return svc.set_toggle(
        current_user.id, _parse_uuid(question_id, "question_id"), payload.is_active
    )


@router.patch("/questions/{question_id}/overrides", response_model=QuestionResponse)
def override_question(
    question_id: str,
    payload: OverridesRequest,
    current_user: User = Depends(require_doctor_user),
    svc: QuestionnaireService = Depends(get_questionnaire_service),
):
    return svc.set_overrides(
        current_user.id,
        _parse_uuid(question_id, "question_id"),
        is_required=payload.is_required,
        show_in_history=payload.show_in_history,
    )


@router.get("/templates", response_model=List[TemplateResponse])
def list_templates(
    current_user: User = Depends(require_doctor_user),
    svc: QuestionnaireService = Depends(get_questionnaire_service),
):
    return svc.list_templates(current_user.id)


@router.post(
    "/templates",
    response_model=TemplateDetailResponse,
    status_code=http_status.HTTP_201_CREATED,
)
def create_template(
    payload: TemplateCreateRequest,
    current_user: User = Depends(require_doctor_user),
    svc: QuestionnaireService = Depends(get_questionnaire_service),
):
    return svc.create_template(current_user.id, payload)


@router.get("/templates/{template_id}", response_model=TemplateDetailResponse)
def get_template(
    template_id: str,
    current_user: User = Depends(require_doctor_user),
    svc: QuestionnaireService = Depends(get_questionnaire_service),
):
    return svc.get_template(current_user.id, _parse_uuid(template_id, "template_id"))


@router.patch("/templates/{template_id}", response_model=TemplateDetailResponse)
def update_template(
    template_id: str,
    payload: TemplateUpdateRequest,
    current_user: User = Depends(require_doctor_user),
    svc: QuestionnaireService = Depends(get_questionnaire_service),
):
    return svc.update_template(
        current_user.id, _parse_uuid(template_id, "template_id"), payload
    )


@router.delete("/templates/{template_id}", status_code=http_status.HTTP_204_NO_CONTENT)
def delete_template(
    template_id: str,
    current_user: User = Depends(require_doctor_user),
    svc: QuestionnaireService = Depends(get_questionnaire_service),
):
    svc.delete_template(current_user.id, _parse_uuid(template_id, "template_id"))
    return None


@router.put(
    "/templates/{template_id}/questions",
    response_model=TemplateDetailResponse,
)
def upsert_template_questions(
    template_id: str,
    payload: TemplateQuestionsUpsertRequest,
    current_user: User = Depends(require_doctor_user),
    svc: QuestionnaireService = Depends(get_questionnaire_service),
):
    return svc.upsert_template_questions(
        current_user.id, _parse_uuid(template_id, "template_id"), payload
    )


@router.post(
    "/invitations",
    response_model=QuestionnaireInvitationSendResponse,
    status_code=http_status.HTTP_201_CREATED,
)
def create_invitation(
    payload: QuestionnaireSendInvitationRequest,
    current_user: User = Depends(require_doctor_user),
    svc: QuestionnaireService = Depends(get_questionnaire_service),
):
    return svc.create_invitation_with_email(current_user.id, payload)


@router.get(
    "/invitations/{invitation_id}",
    response_model=QuestionnaireInvitationSummaryResponse,
)
def get_invitation(
    invitation_id: str,
    current_user: User = Depends(require_doctor_user),
    svc: QuestionnaireService = Depends(get_questionnaire_service),
):
    return svc.get_invitation_summary(
        current_user.id,
        _parse_uuid(invitation_id, "invitation_id"),
    )


@router.get(
    "/public/{token}",
    response_model=PublicInvitationViewResponse,
)
def get_public_invitation(
    token: str,
    svc: QuestionnaireService = Depends(get_questionnaire_service),
):
    return svc.get_public_invitation_view(token)


@router.post(
    "/public/{token}/submit",
    response_model=PublicInvitationSubmitResponse,
)
def submit_public_invitation(
    token: str,
    payload: PublicInvitationSubmitRequest,
    svc: QuestionnaireService = Depends(get_questionnaire_service),
):
    return svc.submit_public_invitation_with_notify(token, payload)


@router.get(
    "/patients/{patient_id}/responses",
    response_model=List[PatientQuestionnaireAnswerView],
)
def get_patient_questionnaire_responses(
    patient_id: str,
    current_user: User = Depends(require_doctor_user),
    svc: QuestionnaireService = Depends(get_questionnaire_service),
):
    pat_uuid = _parse_uuid(patient_id, "patient_id")
    return svc.list_patient_questionnaire_answers(current_user.id, pat_uuid)
