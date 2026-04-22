"""Rutas del módulo de cuestionarios de salud (solo doctor)."""

from __future__ import annotations

import uuid
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
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
from app.models.user import User
from app.repositories.questionnaire_repository import QuestionnaireRepository

router = APIRouter()


StatusFilter = Literal["all", "active", "inactive"]


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
