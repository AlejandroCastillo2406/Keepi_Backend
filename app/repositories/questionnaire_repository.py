from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session
from app.models.questionnaire_invitation import (
    DYNAMIC_QUESTIONNAIRE_MAX_QUESTIONS,
    IntakeSectionView,
    InvitationQuestionView,
    PublicIntakeSectionSubmitResponse,
    PublicInvitationSubmitRequest,
    PublicInvitationSubmitResponse,
    PublicInvitationViewResponse,
    QuestionnaireInvitation,
    QuestionnaireInvitationAnswer,
    QuestionnaireInvitationItem,
    QuestionnaireInvitationSummaryResponse,
    QuestionnaireSendInvitationRequest,
)
from app.services.medical.intake_sections import (
    build_intake_sections_for_invitation,
    intake_is_complete,
    merge_intake_section,
)
from app.models.questionnaire import (
    DoctorQuestionOverride,
    Question,
    RESPONSE_TYPES,
    QuestionCreateRequest,
    QuestionResponse,
    QuestionUpdateRequest,
    Specialty,
    SpecialtyResponse,
    SpecialtySummary,
    Template,
    TemplateCreateRequest,
    TemplateDetailResponse,
    TemplateQuestion,
    TemplateQuestionsUpsertRequest,
    TemplateResponse,
    TemplateUpdateRequest,
)
from app.models.user import User


def _as_uuid(value: Optional[str]) -> Optional[uuid.UUID]:
    if value is None or value == "":
        return None
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="ID inválido"
        ) from exc


def _coalesce(override_val: Optional[bool], default_val: bool) -> bool:
    return default_val if override_val is None else bool(override_val)


def _effective_fields(
    q: Question, override: Optional[DoctorQuestionOverride]
) -> dict[str, bool]:
    return {
        "is_active": _coalesce(
            override.is_active if override else None, bool(q.is_active_default)
        ),
        "is_required": _coalesce(
            override.is_required if override else None, bool(q.is_required_default)
        ),
        "show_in_history": _coalesce(
            override.show_in_history if override else None,
            bool(q.show_in_history_default),
        ),
    }


def _question_to_dto(
    q: Question,
    override: Optional[DoctorQuestionOverride],
    specialty: Optional[Specialty],
    doctor_id: uuid.UUID,
) -> QuestionResponse:
    eff = _effective_fields(q, override)
    return QuestionResponse(
        id=str(q.id),
        specialty_id=str(q.specialty_id) if q.specialty_id else None,
        specialty_name=specialty.name if specialty else None,
        origin=q.origin,
        owner_user_id=str(q.owner_user_id) if q.owner_user_id else None,
        is_mine=bool(q.owner_user_id and q.owner_user_id == doctor_id),
        text=q.text,
        response_type=q.response_type,
        options=list(q.options) if q.options else None,
        help_text=q.help_text,
        is_active=eff["is_active"],
        is_required=eff["is_required"],
        show_in_history=eff["show_in_history"],
        is_required_default=bool(q.is_required_default),
        show_in_history_default=bool(q.show_in_history_default),
        is_active_default=bool(q.is_active_default),
        created_at=q.created_at,
        updated_at=q.updated_at,
    )


def _specialty_to_dto(spec: Specialty) -> SpecialtyResponse:
    return SpecialtyResponse(
        id=str(spec.id),
        slug=spec.slug,
        name=spec.name,
        description=spec.description,
        icon=spec.icon,
        sort_order=int(spec.sort_order or 0),
    )


class QuestionnaireRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def has_any_specialty_row(self) -> bool:
        return self._db.query(Specialty.id).first() is not None

    def has_any_question_row(self) -> bool:
        return self._db.query(Question.id).first() is not None

    def list_specialties(self) -> List[Specialty]:
        return (
            self._db.query(Specialty)
            .order_by(Specialty.sort_order.asc(), Specialty.name.asc())
            .all()
        )

    def list_specialties_with_counts(
        self, doctor_id: uuid.UUID
    ) -> List[SpecialtySummary]:
        specialties = self.list_specialties()
        summaries: List[SpecialtySummary] = []
        for spec in specialties:
            questions = self._fetch_visible_questions(
                doctor_id, specialty_id=spec.id, only_globals=False
            )
            total = len(questions)
            active = sum(
                1 for q, ov in questions if _effective_fields(q, ov)["is_active"]
            )
            summaries.append(
                SpecialtySummary(
                    **_specialty_to_dto(spec).model_dump(),
                    total_questions=total,
                    total_active=active,
                )
            )
        return summaries

    def get_specialty(self, specialty_id: uuid.UUID) -> Specialty:
        spec = self._db.query(Specialty).filter(Specialty.id == specialty_id).first()
        if not spec:
            raise HTTPException(status_code=404, detail="Especialidad no encontrada")
        return spec

    def _fetch_visible_questions(
        self,
        doctor_id: uuid.UUID,
        *,
        specialty_id: Optional[uuid.UUID] = None,
        only_globals: bool = False,
    ) -> List[tuple[Question, Optional[DoctorQuestionOverride]]]:
        ownership_filter = or_(
            Question.origin == "system",
            Question.owner_user_id == doctor_id,
        )

        q = self._db.query(Question).filter(ownership_filter)
        if only_globals:
            q = q.filter(Question.specialty_id.is_(None))
        elif specialty_id is not None:
            q = q.filter(Question.specialty_id == specialty_id)

        questions = q.order_by(
            Question.sort_order.asc(), Question.created_at.asc()
        ).all()

        if not questions:
            return []

        overrides = (
            self._db.query(DoctorQuestionOverride)
            .filter(
                DoctorQuestionOverride.doctor_id == doctor_id,
                DoctorQuestionOverride.question_id.in_([x.id for x in questions]),
            )
            .all()
        )
        by_qid = {ov.question_id: ov for ov in overrides}
        return [(x, by_qid.get(x.id)) for x in questions]

    def list_questions(
        self,
        doctor_id: uuid.UUID,
        *,
        specialty_id: Optional[uuid.UUID] = None,
        only_globals: bool = False,
        status_filter: str = "all",
    ) -> List[QuestionResponse]:
        rows = self._fetch_visible_questions(
            doctor_id, specialty_id=specialty_id, only_globals=only_globals
        )

        spec_ids = {q.specialty_id for q, _ in rows if q.specialty_id}
        specialties_by_id: dict[uuid.UUID, Specialty] = {}
        if spec_ids:
            for s in self._db.query(Specialty).filter(Specialty.id.in_(spec_ids)).all():
                specialties_by_id[s.id] = s

        out: List[QuestionResponse] = []
        for q, ov in rows:
            eff = _effective_fields(q, ov)
            if status_filter == "active" and not eff["is_active"]:
                continue
            if status_filter == "inactive" and eff["is_active"]:
                continue
            out.append(
                _question_to_dto(
                    q,
                    ov,
                    specialties_by_id.get(q.specialty_id) if q.specialty_id else None,
                    doctor_id,
                )
            )
        return out

    def get_question_dto(
        self, doctor_id: uuid.UUID, question_id: uuid.UUID
    ) -> QuestionResponse:
        q = self._db.query(Question).filter(Question.id == question_id).first()
        if not q:
            raise HTTPException(status_code=404, detail="Pregunta no encontrada")

        if q.origin == "custom" and q.owner_user_id != doctor_id:
            raise HTTPException(status_code=404, detail="Pregunta no encontrada")
        ov = (
            self._db.query(DoctorQuestionOverride)
            .filter(
                DoctorQuestionOverride.doctor_id == doctor_id,
                DoctorQuestionOverride.question_id == q.id,
            )
            .first()
        )
        spec = (
            self._db.query(Specialty).filter(Specialty.id == q.specialty_id).first()
            if q.specialty_id
            else None
        )
        return _question_to_dto(q, ov, spec, doctor_id)

    def create_custom_question(
        self, doctor_id: uuid.UUID, data: QuestionCreateRequest
    ) -> QuestionResponse:
        if data.response_type in ("single_choice", "multi_choice"):
            if not data.options or len(data.options) < 2:
                raise HTTPException(
                    status_code=400,
                    detail="Debe incluir al menos 2 opciones para este tipo de respuesta",
                )
        specialty_uuid = _as_uuid(data.specialty_id)
        if specialty_uuid is not None:
            self.get_specialty(specialty_uuid)

        next_order = (
            self._db.query(func.coalesce(func.max(Question.sort_order), 0))
            .filter(Question.owner_user_id == doctor_id)
            .scalar()
            or 0
        )

        q = Question(
            specialty_id=specialty_uuid,
            owner_user_id=doctor_id,
            origin="custom",
            text=data.text.strip(),
            response_type=data.response_type,
            options=data.options,
            help_text=data.help_text,
            is_required_default=bool(data.is_required),
            show_in_history_default=bool(data.show_in_history),
            is_active_default=True,
            sort_order=int(next_order) + 1,
        )
        self._db.add(q)
        self._db.commit()
        self._db.refresh(q)
        return self.get_question_dto(doctor_id, q.id)

    def update_custom_question(
        self,
        doctor_id: uuid.UUID,
        question_id: uuid.UUID,
        data: QuestionUpdateRequest,
    ) -> QuestionResponse:
        q = self._db.query(Question).filter(Question.id == question_id).first()
        if not q:
            raise HTTPException(status_code=404, detail="Pregunta no encontrada")
        if q.origin != "custom" or q.owner_user_id != doctor_id:
            raise HTTPException(
                status_code=403,
                detail="Solo puedes editar tus preguntas personalizadas",
            )

        if data.text is not None:
            q.text = data.text.strip()
        if data.response_type is not None:
            if data.response_type not in RESPONSE_TYPES:
                raise HTTPException(
                    status_code=400, detail="Tipo de respuesta inválido"
                )
            q.response_type = data.response_type
        if data.options is not None:
            q.options = data.options
        if data.help_text is not None:
            q.help_text = data.help_text or None
        if data.is_required is not None:
            q.is_required_default = bool(data.is_required)
        if data.show_in_history is not None:
            q.show_in_history_default = bool(data.show_in_history)
        if data.specialty_id is not None or "specialty_id" in data.model_fields_set:
            spec_uuid = _as_uuid(data.specialty_id) if data.specialty_id else None
            if spec_uuid is not None:
                self.get_specialty(spec_uuid)
            q.specialty_id = spec_uuid

        if q.response_type in ("single_choice", "multi_choice"):
            if not q.options or len(q.options) < 2:
                raise HTTPException(
                    status_code=400,
                    detail="Debe incluir al menos 2 opciones para este tipo de respuesta",
                )

        self._db.commit()
        self._db.refresh(q)
        return self.get_question_dto(doctor_id, q.id)

    def delete_custom_question(
        self, doctor_id: uuid.UUID, question_id: uuid.UUID
    ) -> None:
        q = self._db.query(Question).filter(Question.id == question_id).first()
        if not q:
            raise HTTPException(status_code=404, detail="Pregunta no encontrada")
        if q.origin != "custom" or q.owner_user_id != doctor_id:
            raise HTTPException(
                status_code=403,
                detail="Solo puedes eliminar tus preguntas personalizadas",
            )
        self._db.delete(q)
        self._db.commit()

    def _load_override(
        self, doctor_id: uuid.UUID, question_id: uuid.UUID
    ) -> Optional[DoctorQuestionOverride]:
        return (
            self._db.query(DoctorQuestionOverride)
            .filter(
                DoctorQuestionOverride.doctor_id == doctor_id,
                DoctorQuestionOverride.question_id == question_id,
            )
            .first()
        )

    def _ensure_togglable(
        self, doctor_id: uuid.UUID, question_id: uuid.UUID
    ) -> Question:
        q = self._db.query(Question).filter(Question.id == question_id).first()
        if not q:
            raise HTTPException(status_code=404, detail="Pregunta no encontrada")
        if q.origin == "custom" and q.owner_user_id != doctor_id:
            raise HTTPException(status_code=403, detail="Pregunta no disponible")
        return q

    def set_toggle(
        self, doctor_id: uuid.UUID, question_id: uuid.UUID, is_active: bool
    ) -> QuestionResponse:
        q = self._ensure_togglable(doctor_id, question_id)

        if q.origin == "custom":
            q.is_active_default = bool(is_active)
            self._db.commit()
            return self.get_question_dto(doctor_id, q.id)

        ov = self._load_override(doctor_id, question_id)
        if ov is None:
            ov = DoctorQuestionOverride(
                doctor_id=doctor_id,
                question_id=question_id,
                is_active=bool(is_active),
            )
            self._db.add(ov)
        else:
            ov.is_active = bool(is_active)
        self._db.commit()
        return self.get_question_dto(doctor_id, q.id)

    def set_overrides(
        self,
        doctor_id: uuid.UUID,
        question_id: uuid.UUID,
        *,
        is_required: Optional[bool],
        show_in_history: Optional[bool],
    ) -> QuestionResponse:
        q = self._ensure_togglable(doctor_id, question_id)

        if q.origin == "custom":
            if is_required is not None:
                q.is_required_default = bool(is_required)
            if show_in_history is not None:
                q.show_in_history_default = bool(show_in_history)
            self._db.commit()
            return self.get_question_dto(doctor_id, q.id)

        ov = self._load_override(doctor_id, question_id)
        if ov is None:
            ov = DoctorQuestionOverride(
                doctor_id=doctor_id,
                question_id=question_id,
                is_required=is_required,
                show_in_history=show_in_history,
            )
            self._db.add(ov)
        else:
            if is_required is not None:
                ov.is_required = is_required
            if show_in_history is not None:
                ov.show_in_history = show_in_history
        self._db.commit()
        return self.get_question_dto(doctor_id, q.id)

    def list_templates(self, doctor_id: uuid.UUID) -> List[TemplateResponse]:
        rows = (
            self._db.query(Template)
            .filter(Template.doctor_id == doctor_id)
            .order_by(Template.created_at.desc())
            .all()
        )
        if not rows:
            return []

        counts = dict(
            self._db.query(
                TemplateQuestion.template_id, func.count(TemplateQuestion.id)
            )
            .filter(TemplateQuestion.template_id.in_([r.id for r in rows]))
            .group_by(TemplateQuestion.template_id)
            .all()
        )

        spec_ids = {r.specialty_id for r in rows if r.specialty_id}
        specialties_by_id: dict[uuid.UUID, Specialty] = {}
        if spec_ids:
            for s in self._db.query(Specialty).filter(Specialty.id.in_(spec_ids)).all():
                specialties_by_id[s.id] = s

        return [
            TemplateResponse(
                id=str(r.id),
                doctor_id=str(r.doctor_id),
                specialty_id=str(r.specialty_id) if r.specialty_id else None,
                specialty_name=(
                    specialties_by_id.get(r.specialty_id).name
                    if r.specialty_id and r.specialty_id in specialties_by_id
                    else None
                ),
                name=r.name,
                description=r.description,
                total_questions=int(counts.get(r.id, 0)),
                created_at=r.created_at,
                updated_at=r.updated_at,
            )
            for r in rows
        ]

    def get_template(
        self, doctor_id: uuid.UUID, template_id: uuid.UUID
    ) -> TemplateDetailResponse:
        t = (
            self._db.query(Template)
            .filter(Template.id == template_id, Template.doctor_id == doctor_id)
            .first()
        )
        if not t:
            raise HTTPException(status_code=404, detail="Plantilla no encontrada")

        items = (
            self._db.query(TemplateQuestion)
            .filter(TemplateQuestion.template_id == t.id)
            .order_by(
                TemplateQuestion.sort_order.asc(), TemplateQuestion.created_at.asc()
            )
            .all()
        )
        question_ids = [i.question_id for i in items]

        question_dtos: List[QuestionResponse] = []
        if question_ids:
            questions = (
                self._db.query(Question).filter(Question.id.in_(question_ids)).all()
            )
            q_by_id = {q.id: q for q in questions}
            overrides = (
                self._db.query(DoctorQuestionOverride)
                .filter(
                    DoctorQuestionOverride.doctor_id == doctor_id,
                    DoctorQuestionOverride.question_id.in_(question_ids),
                )
                .all()
            )
            ov_by_qid = {o.question_id: o for o in overrides}

            spec_ids = {q.specialty_id for q in questions if q.specialty_id}
            spec_by_id: dict[uuid.UUID, Specialty] = {}
            if spec_ids:
                for s in (
                    self._db.query(Specialty).filter(Specialty.id.in_(spec_ids)).all()
                ):
                    spec_by_id[s.id] = s

            for item in items:
                q = q_by_id.get(item.question_id)
                if not q:
                    continue
                question_dtos.append(
                    _question_to_dto(
                        q,
                        ov_by_qid.get(q.id),
                        spec_by_id.get(q.specialty_id) if q.specialty_id else None,
                        doctor_id,
                    )
                )

        spec = (
            self._db.query(Specialty).filter(Specialty.id == t.specialty_id).first()
            if t.specialty_id
            else None
        )
        return TemplateDetailResponse(
            id=str(t.id),
            doctor_id=str(t.doctor_id),
            specialty_id=str(t.specialty_id) if t.specialty_id else None,
            specialty_name=spec.name if spec else None,
            name=t.name,
            description=t.description,
            total_questions=len(question_dtos),
            created_at=t.created_at,
            updated_at=t.updated_at,
            questions=question_dtos,
        )

    def create_template(
        self, doctor_id: uuid.UUID, data: TemplateCreateRequest
    ) -> TemplateDetailResponse:
        spec_uuid = _as_uuid(data.specialty_id) if data.specialty_id else None
        if spec_uuid is not None:
            self.get_specialty(spec_uuid)

        exists = (
            self._db.query(Template)
            .filter(Template.doctor_id == doctor_id, Template.name == data.name.strip())
            .first()
        )
        if exists:
            raise HTTPException(
                status_code=409, detail="Ya tienes una plantilla con ese nombre"
            )

        t = Template(
            doctor_id=doctor_id,
            specialty_id=spec_uuid,
            name=data.name.strip(),
            description=(data.description or None),
        )
        self._db.add(t)
        self._db.commit()
        self._db.refresh(t)
        return self.get_template(doctor_id, t.id)

    def update_template(
        self,
        doctor_id: uuid.UUID,
        template_id: uuid.UUID,
        data: TemplateUpdateRequest,
    ) -> TemplateDetailResponse:
        t = (
            self._db.query(Template)
            .filter(Template.id == template_id, Template.doctor_id == doctor_id)
            .first()
        )
        if not t:
            raise HTTPException(status_code=404, detail="Plantilla no encontrada")

        if data.name is not None:
            new_name = data.name.strip()
            if new_name != t.name:
                dup = (
                    self._db.query(Template)
                    .filter(
                        Template.doctor_id == doctor_id,
                        Template.name == new_name,
                        Template.id != t.id,
                    )
                    .first()
                )
                if dup:
                    raise HTTPException(
                        status_code=409,
                        detail="Ya tienes una plantilla con ese nombre",
                    )
                t.name = new_name
        if data.description is not None:
            t.description = data.description or None
        if "specialty_id" in data.model_fields_set:
            spec_uuid = _as_uuid(data.specialty_id) if data.specialty_id else None
            if spec_uuid is not None:
                self.get_specialty(spec_uuid)
            t.specialty_id = spec_uuid

        self._db.commit()
        return self.get_template(doctor_id, t.id)

    def delete_template(self, doctor_id: uuid.UUID, template_id: uuid.UUID) -> None:
        t = (
            self._db.query(Template)
            .filter(Template.id == template_id, Template.doctor_id == doctor_id)
            .first()
        )
        if not t:
            raise HTTPException(status_code=404, detail="Plantilla no encontrada")
        self._db.delete(t)
        self._db.commit()

    def upsert_template_questions(
        self,
        doctor_id: uuid.UUID,
        template_id: uuid.UUID,
        data: TemplateQuestionsUpsertRequest,
    ) -> TemplateDetailResponse:
        t = (
            self._db.query(Template)
            .filter(Template.id == template_id, Template.doctor_id == doctor_id)
            .first()
        )
        if not t:
            raise HTTPException(status_code=404, detail="Plantilla no encontrada")

        question_uuids: List[uuid.UUID] = []
        for it in data.items:
            qid = _as_uuid(it.question_id)
            if qid is None:
                raise HTTPException(status_code=400, detail="question_id inválido")
            question_uuids.append(qid)

        if question_uuids:
            visible = (
                self._db.query(Question.id)
                .filter(
                    Question.id.in_(question_uuids),
                    or_(
                        Question.origin == "system",
                        Question.owner_user_id == doctor_id,
                    ),
                )
                .all()
            )
            visible_ids = {row[0] for row in visible}
            missing = [str(q) for q in question_uuids if q not in visible_ids]
            if missing:
                raise HTTPException(
                    status_code=400,
                    detail=f"Preguntas no disponibles: {', '.join(missing)}",
                )

        self._db.query(TemplateQuestion).filter(
            TemplateQuestion.template_id == t.id
        ).delete(synchronize_session=False)

        seen: set[uuid.UUID] = set()
        for it in data.items:
            qid = _as_uuid(it.question_id)
            if qid is None or qid in seen:
                continue
            seen.add(qid)
            self._db.add(
                TemplateQuestion(
                    template_id=t.id,
                    question_id=qid,
                    sort_order=int(it.sort_order or 0),
                )
            )
        self._db.commit()
        return self.get_template(doctor_id, t.id)

    @staticmethod
    def _hash_token(raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    @staticmethod
    def _generate_invitation_secret_token() -> str:
        return secrets.token_urlsafe(32)

    def _get_invitation_for_public_token(
        self, raw_token: str
    ) -> QuestionnaireInvitation:
        stripped = (raw_token or "").strip()
        if not stripped:
            raise HTTPException(status_code=400, detail="Token inválido")
        token_hash = self._hash_token(stripped)
        inv = (
            self._db.query(QuestionnaireInvitation)
            .filter(QuestionnaireInvitation.token_hash == token_hash)
            .first()
        )
        if not inv:
            raise HTTPException(status_code=404, detail="Invitación no encontrada")
        return inv

    @staticmethod
    def _invitation_to_summary(
        inv: QuestionnaireInvitation, total_questions: int
    ) -> QuestionnaireInvitationSummaryResponse:
        return QuestionnaireInvitationSummaryResponse(
            id=str(inv.id),
            doctor_id=str(inv.doctor_id),
            patient_id=str(inv.patient_id),
            patient_name=inv.patient_name_snapshot,
            patient_email=inv.patient_email_snapshot,
            status=inv.status,
            created_at=inv.created_at,
            expires_at=inv.expires_at,
            completed_at=inv.completed_at,
            total_questions=total_questions,
        )

    def _load_patient_owned_by_doctor(
        self, doctor_id: uuid.UUID, patient_id: uuid.UUID
    ) -> User:
        patient = (
            self._db.query(User)
            .filter(User.id == patient_id, User.created_by_user_id == doctor_id)
            .first()
        )
        if not patient:
            raise HTTPException(
                status_code=404, detail="Paciente no vinculado al doctor"
            )
        return patient

    def _build_snapshot_questions(
        self,
        doctor_id: uuid.UUID,
        template_ids: List[uuid.UUID],
        extra_question_ids: List[uuid.UUID],
    ) -> List[dict]:
        rows: List[dict] = []
        seen: set[uuid.UUID] = set()

        for t_id in template_ids:
            template = (
                self._db.query(Template)
                .filter(Template.id == t_id, Template.doctor_id == doctor_id)
                .first()
            )
            if not template:
                raise HTTPException(
                    status_code=404, detail=f"Plantilla no encontrada: {t_id}"
                )

            items = (
                self._db.query(TemplateQuestion)
                .filter(TemplateQuestion.template_id == template.id)
                .order_by(TemplateQuestion.sort_order.asc())
                .all()
            )
            question_ids = [i.question_id for i in items]
            if not question_ids:
                continue

            questions = (
                self._db.query(Question).filter(Question.id.in_(question_ids)).all()
            )
            question_by_id = {q.id: q for q in questions}
            specialties = {}
            spec_ids = {q.specialty_id for q in questions if q.specialty_id}
            if spec_ids:
                for s in (
                    self._db.query(Specialty).filter(Specialty.id.in_(spec_ids)).all()
                ):
                    specialties[s.id] = s.name

            for item in items:
                q = question_by_id.get(item.question_id)
                if not q or q.id in seen:
                    continue
                seen.add(q.id)
                rows.append(
                    {
                        "question_id": q.id,
                        "question_text": q.text,
                        "response_type": q.response_type,
                        "options": list(q.options) if q.options else None,
                        "help_text": q.help_text,
                        "is_required": bool(q.is_required_default),
                        "specialty_name": (
                            specialties.get(q.specialty_id) if q.specialty_id else None
                        ),
                        "template_name": template.name,
                    }
                )

        if extra_question_ids:
            questions = (
                self._db.query(Question)
                .filter(
                    Question.id.in_(extra_question_ids),
                    or_(
                        Question.origin == "system", Question.owner_user_id == doctor_id
                    ),
                )
                .all()
            )
            available = {q.id: q for q in questions}
            missing = [str(qid) for qid in extra_question_ids if qid not in available]
            if missing:
                raise HTTPException(
                    status_code=400,
                    detail=f"Preguntas no disponibles: {', '.join(missing)}",
                )

            spec_ids = {q.specialty_id for q in questions if q.specialty_id}
            specialties = {}
            if spec_ids:
                for s in (
                    self._db.query(Specialty).filter(Specialty.id.in_(spec_ids)).all()
                ):
                    specialties[s.id] = s.name

            for qid in extra_question_ids:
                q = available[qid]
                if q.id in seen:
                    continue
                seen.add(q.id)
                rows.append(
                    {
                        "question_id": q.id,
                        "question_text": q.text,
                        "response_type": q.response_type,
                        "options": list(q.options) if q.options else None,
                        "help_text": q.help_text,
                        "is_required": bool(q.is_required_default),
                        "specialty_name": (
                            specialties.get(q.specialty_id) if q.specialty_id else None
                        ),
                        "template_name": None,
                    }
                )

        if not rows:
            raise HTTPException(
                status_code=400, detail="No hay preguntas para enviar en la invitación"
            )
        return rows

    @staticmethod
    def _is_dynamic_invitation(data: QuestionnaireSendInvitationRequest) -> bool:
        return bool(getattr(data, "use_dynamic_questionnaire", False))

    @staticmethod
    def _intake_context_from_payload(data) -> Optional[dict]:
        ctx: dict = {}
        for key in (
            "phone",
            "birth_date",
            "sex",
            "consultation_reason",
            "specialty",
        ):
            val = getattr(data, key, None)
            if val is not None and str(val).strip():
                ctx[key] = str(val).strip()
        return ctx or None

    @staticmethod
    def _enable_clinical_intake_from_payload(data) -> bool:
        flag = getattr(data, "enable_clinical_intake", True)
        if flag in (False, 0, "0", "false", "False", "no", "off"):
            return False
        return True

    @staticmethod
    def _intake_only_from_payload(data) -> bool:
        flag = getattr(data, "intake_only", False)
        if flag in (True, 1, "1", "true", "True", "yes", "on"):
            return True
        return False

    def _invitation_item_count(self, invitation_id: uuid.UUID) -> int:
        return (
            self._db.query(QuestionnaireInvitationItem)
            .filter(QuestionnaireInvitationItem.invitation_id == invitation_id)
            .count()
        )

    def _is_intake_only_invitation(self, inv: QuestionnaireInvitation) -> bool:
        if not bool(getattr(inv, "enable_clinical_intake", False)):
            return False
        if bool(getattr(inv, "is_dynamic", False)):
            return False
        return self._invitation_item_count(inv.id) == 0

    def _apply_clinical_intake_to_invitation(
        self, invitation: QuestionnaireInvitation, data
    ) -> None:
        intake_only = self._intake_only_from_payload(data)
        invitation.enable_clinical_intake = (
            True
            if intake_only
            else self._enable_clinical_intake_from_payload(data)
        )
        invitation.intake_context = self._intake_context_from_payload(data)
        invitation.intake_responses = {}

    def _intake_meta_for_invitation(
        self, inv: QuestionnaireInvitation
    ) -> tuple[bool, bool, list, Optional[str], Optional[str]]:
        enable = bool(getattr(inv, "enable_clinical_intake", False))
        ctx = inv.intake_context if isinstance(inv.intake_context, dict) else {}
        saved = inv.intake_responses if isinstance(inv.intake_responses, dict) else {}
        sections_raw = (
            build_intake_sections_for_invitation(ctx, saved) if enable else []
        )
        sections = [IntakeSectionView.model_validate(s) for s in sections_raw]
        completed = inv.intake_completed_at is not None
        if enable and not completed:
            completed = intake_is_complete(sections_raw, saved)
        specialty = ctx.get("specialty")
        reason = ctx.get("consultation_reason")
        return enable, completed, sections, specialty, reason

    def save_public_intake_section(
        self, raw_token: str, section_id: str, answers: dict
    ) -> PublicIntakeSectionSubmitResponse:
        inv = self._get_invitation_for_public_token(raw_token)
        inv = self._mark_expired_if_needed(inv)
        if inv.status != "pending":
            raise HTTPException(
                status_code=400, detail="Esta invitación ya no está disponible"
            )
        if not bool(getattr(inv, "enable_clinical_intake", False)):
            raise HTTPException(
                status_code=400,
                detail="Esta invitación no incluye ficha clínica previa",
            )

        ctx = inv.intake_context if isinstance(inv.intake_context, dict) else {}
        merged = merge_intake_section(
            inv.intake_responses if isinstance(inv.intake_responses, dict) else {},
            section_id.strip(),
            answers or {},
        )
        inv.intake_responses = merged
        sections_raw = build_intake_sections_for_invitation(ctx, merged)
        sections = [IntakeSectionView.model_validate(s) for s in sections_raw]
        intake_only = self._is_intake_only_invitation(inv)
        if intake_is_complete(sections_raw, merged):
            inv.intake_completed_at = datetime.now(timezone.utc)
            if intake_only:
                now = datetime.now(timezone.utc)
                inv.status = "completed"
                inv.used_at = now
                inv.completed_at = now
        self._db.commit()
        self._db.refresh(inv)
        completed = inv.intake_completed_at is not None
        return PublicIntakeSectionSubmitResponse(
            intake_completed=completed,
            intake_sections=sections,
            intake_only=intake_only,
            collect_prior_documents=bool(
                getattr(inv, "collect_prior_documents", False)
            ),
        ), inv if intake_only and completed else None

    def create_invitation_batch(
        self, doctor_id: uuid.UUID, data: QuestionnaireSendInvitationRequest
    ) -> tuple[QuestionnaireInvitationSummaryResponse, str]:
        if self._is_dynamic_invitation(data):
            if self._intake_only_from_payload(data):
                raise HTTPException(
                    status_code=400,
                    detail="Solo ficha clínica no puede combinarse con cuestionario dinámico",
                )
            return self._create_dynamic_invitation_batch(doctor_id, data)

        intake_only = self._intake_only_from_payload(data)
        has_questions = bool(data.template_ids or data.question_ids)
        enable_intake = self._enable_clinical_intake_from_payload(data)
        if not intake_only and not has_questions and enable_intake:
            intake_only = True
        if intake_only:
            if has_questions:
                raise HTTPException(
                    status_code=400,
                    detail="Solo ficha clínica no puede combinarse con plantillas o preguntas",
                )
        elif not has_questions:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Indica plantillas, preguntas, cuestionario dinámico "
                    "o activa ficha clínica previa (intake_only)"
                ),
            )

        patient_id = _as_uuid(data.patient_id)
        if patient_id is None:
            raise HTTPException(status_code=400, detail="patient_id inválido")
        patient = self._load_patient_owned_by_doctor(doctor_id, patient_id)

        if intake_only:
            snapshot: List[dict] = []
        else:
            template_ids = []
            for tid in data.template_ids:
                uid = _as_uuid(tid)
                if uid is None:
                    raise HTTPException(
                        status_code=400, detail=f"template_id inválido: {tid}"
                    )
                template_ids.append(uid)

            question_ids = []
            for qid in data.question_ids:
                uid = _as_uuid(qid)
                if uid is None:
                    raise HTTPException(
                        status_code=400, detail=f"question_id inválido: {qid}"
                    )
                question_ids.append(uid)

            snapshot = self._build_snapshot_questions(
                doctor_id, template_ids, question_ids
            )

        hours = 24
        expires_at = datetime.now(timezone.utc) + timedelta(hours=hours)

        invitation = QuestionnaireInvitation(
            doctor_id=doctor_id,
            patient_id=patient.id,
            patient_email_snapshot=patient.email,
            patient_name_snapshot=patient.name,
            token_hash="__pending__",
            status="pending",
            expires_at=expires_at,
            collect_prior_documents=bool(data.collect_prior_documents),
        )
        self._apply_clinical_intake_to_invitation(invitation, data)
        self._db.add(invitation)
        self._db.flush()

        raw_token = self._generate_invitation_secret_token()
        invitation.token_hash = self._hash_token(raw_token)

        for idx, item in enumerate(snapshot):
            self._db.add(
                QuestionnaireInvitationItem(
                    invitation_id=invitation.id,
                    question_id=item["question_id"],
                    question_text_snapshot=item["question_text"],
                    response_type_snapshot=item["response_type"],
                    options_snapshot=item["options"],
                    help_text_snapshot=item["help_text"],
                    is_required_snapshot=item["is_required"],
                    specialty_name_snapshot=item["specialty_name"],
                    template_name_snapshot=item["template_name"],
                    sort_order=idx,
                )
            )
        self._db.commit()
        self._db.refresh(invitation)
        return self._invitation_to_summary(invitation, len(snapshot)), raw_token

    def _create_dynamic_invitation_batch(
        self, doctor_id: uuid.UUID, data: QuestionnaireSendInvitationRequest
    ) -> tuple[QuestionnaireInvitationSummaryResponse, str]:
        if data.template_ids or data.question_ids:
            raise HTTPException(
                status_code=400,
                detail="El cuestionario dinámico no puede combinarse con plantillas o preguntas fijas",
            )
        patient_id = _as_uuid(data.patient_id)
        if patient_id is None:
            raise HTTPException(status_code=400, detail="patient_id inválido")
        patient = self._load_patient_owned_by_doctor(doctor_id, patient_id)

        expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
        invitation = QuestionnaireInvitation(
            doctor_id=doctor_id,
            patient_id=patient.id,
            patient_email_snapshot=patient.email,
            patient_name_snapshot=patient.name,
            token_hash="__pending__",
            status="pending",
            expires_at=expires_at,
            collect_prior_documents=bool(data.collect_prior_documents),
            is_dynamic=True,
        )
        self._apply_clinical_intake_to_invitation(invitation, data)
        self._db.add(invitation)
        self._db.flush()

        raw_token = self._generate_invitation_secret_token()
        invitation.token_hash = self._hash_token(raw_token)
        self._db.commit()
        self._db.refresh(invitation)
        return (
            self._invitation_to_summary(
                invitation, DYNAMIC_QUESTIONNAIRE_MAX_QUESTIONS
            ),
            raw_token,
        )

    def _invitation_item_to_view(
        self, item: QuestionnaireInvitationItem
    ) -> InvitationQuestionView:
        return InvitationQuestionView(
            item_id=str(item.id),
            question_text=item.question_text_snapshot,
            response_type=item.response_type_snapshot,
            options=list(item.options_snapshot) if item.options_snapshot else None,
            help_text=item.help_text_snapshot,
            is_required=bool(item.is_required_snapshot),
            specialty_name=item.specialty_name_snapshot,
            template_name=item.template_name_snapshot or "Cuestionario dinámico (IA)",
        )

    def count_answered_dynamic_items(self, invitation_id: uuid.UUID) -> int:
        return (
            self._db.query(func.count(QuestionnaireInvitationAnswer.id))
            .join(
                QuestionnaireInvitationItem,
                QuestionnaireInvitationItem.id
                == QuestionnaireInvitationAnswer.invitation_item_id,
            )
            .filter(QuestionnaireInvitationItem.invitation_id == invitation_id)
            .scalar()
            or 0
        )

    def get_pending_dynamic_item(
        self, invitation_id: uuid.UUID
    ) -> Optional[QuestionnaireInvitationItem]:
        items = (
            self._db.query(QuestionnaireInvitationItem)
            .filter(QuestionnaireInvitationItem.invitation_id == invitation_id)
            .order_by(QuestionnaireInvitationItem.sort_order.asc())
            .all()
        )
        for item in items:
            answered = (
                self._db.query(QuestionnaireInvitationAnswer)
                .filter(
                    QuestionnaireInvitationAnswer.invitation_item_id == item.id
                )
                .first()
            )
            if answered is None:
                return item
        return None

    def get_dynamic_conversation(
        self, invitation_id: uuid.UUID
    ) -> List[dict]:
        items = (
            self._db.query(QuestionnaireInvitationItem)
            .filter(QuestionnaireInvitationItem.invitation_id == invitation_id)
            .order_by(QuestionnaireInvitationItem.sort_order.asc())
            .all()
        )
        rows: List[dict] = []
        for item in items:
            ans = (
                self._db.query(QuestionnaireInvitationAnswer)
                .filter(
                    QuestionnaireInvitationAnswer.invitation_item_id == item.id
                )
                .first()
            )
            if ans is None:
                continue
            value = ans.answer_json.get("value") if ans.answer_json else None
            rows.append(
                {
                    "question_text": item.question_text_snapshot,
                    "answer": value,
                }
            )
        return rows

    def add_dynamic_question_item(
        self,
        invitation_id: uuid.UUID,
        *,
        question_text: str,
        response_type: str,
        options: Optional[List[str]],
        help_text: Optional[str],
        is_required: bool,
        sort_order: int,
    ) -> QuestionnaireInvitationItem:
        item = QuestionnaireInvitationItem(
            invitation_id=invitation_id,
            question_id=None,
            question_text_snapshot=question_text,
            response_type_snapshot=response_type,
            options_snapshot=options,
            help_text_snapshot=help_text,
            is_required_snapshot=is_required,
            specialty_name_snapshot=None,
            template_name_snapshot="Cuestionario dinámico (IA)",
            sort_order=sort_order,
        )
        self._db.add(item)
        self._db.commit()
        self._db.refresh(item)
        return item

    def save_dynamic_item_answer(
        self, item: QuestionnaireInvitationItem, answer: Any
    ) -> None:
        existing = (
            self._db.query(QuestionnaireInvitationAnswer)
            .filter(
                QuestionnaireInvitationAnswer.invitation_item_id == item.id
            )
            .first()
        )
        if existing:
            existing.answer_json = {"value": answer}
        else:
            self._db.add(
                QuestionnaireInvitationAnswer(
                    invitation_item_id=item.id,
                    answer_json={"value": answer},
                )
            )
        self._db.commit()

    def complete_invitation(self, invitation: QuestionnaireInvitation) -> None:
        invitation.status = "completed"
        invitation.completed_at = datetime.now(timezone.utc)
        invitation.used_at = datetime.now(timezone.utc)
        self._db.commit()
        self._db.refresh(invitation)

    def _mark_expired_if_needed(
        self, invitation: QuestionnaireInvitation
    ) -> QuestionnaireInvitation:
        if invitation.status == "pending" and invitation.expires_at < datetime.now(
            timezone.utc
        ):
            invitation.status = "expired"
            self._db.commit()
            self._db.refresh(invitation)
        return invitation

    def get_invitation_summary(
        self, doctor_id: uuid.UUID, invitation_id: uuid.UUID
    ) -> QuestionnaireInvitationSummaryResponse:
        inv = (
            self._db.query(QuestionnaireInvitation)
            .filter(
                QuestionnaireInvitation.id == invitation_id,
                QuestionnaireInvitation.doctor_id == doctor_id,
            )
            .first()
        )
        if not inv:
            raise HTTPException(status_code=404, detail="Invitación no encontrada")
        inv = self._mark_expired_if_needed(inv)
        total = (
            self._db.query(func.count(QuestionnaireInvitationItem.id))
            .filter(QuestionnaireInvitationItem.invitation_id == inv.id)
            .scalar()
            or 0
        )
        return self._invitation_to_summary(inv, int(total))

    def get_public_invitation_view(
        self, raw_token: str
    ) -> PublicInvitationViewResponse:
        inv = self._get_invitation_for_public_token(raw_token)
        inv = self._mark_expired_if_needed(inv)

        is_dynamic = bool(getattr(inv, "is_dynamic", False))
        answered_dynamic = (
            self.count_answered_dynamic_items(inv.id) if is_dynamic else 0
        )

        enable_intake, intake_done, intake_sections, specialty, reason = (
            self._intake_meta_for_invitation(inv)
        )
        intake_only = self._is_intake_only_invitation(inv)
        collect_prior = bool(getattr(inv, "collect_prior_documents", False))

        if inv.status != "pending":
            return PublicInvitationViewResponse(
                invitation_id=str(inv.id),
                patient_name=inv.patient_name_snapshot,
                patient_email=inv.patient_email_snapshot,
                status=inv.status,
                expires_at=inv.expires_at,
                questions=[],
                collect_prior_documents=collect_prior,
                is_dynamic=is_dynamic,
                dynamic_max_questions=DYNAMIC_QUESTIONNAIRE_MAX_QUESTIONS,
                dynamic_answered_count=answered_dynamic,
                enable_clinical_intake=enable_intake,
                intake_completed=intake_done,
                intake_only=intake_only,
                intake_sections=intake_sections,
                specialty=specialty,
                consultation_reason=reason,
            )

        if enable_intake and not intake_done:
            return PublicInvitationViewResponse(
                invitation_id=str(inv.id),
                patient_name=inv.patient_name_snapshot,
                patient_email=inv.patient_email_snapshot,
                status=inv.status,
                expires_at=inv.expires_at,
                questions=[],
                collect_prior_documents=collect_prior,
                is_dynamic=is_dynamic,
                dynamic_max_questions=DYNAMIC_QUESTIONNAIRE_MAX_QUESTIONS,
                dynamic_answered_count=answered_dynamic,
                enable_clinical_intake=True,
                intake_completed=False,
                intake_only=intake_only,
                intake_sections=intake_sections,
                specialty=specialty,
                consultation_reason=reason,
            )

        if is_dynamic:
            pending = self.get_pending_dynamic_item(inv.id)
            questions = (
                [self._invitation_item_to_view(pending)] if pending else []
            )
            return PublicInvitationViewResponse(
                invitation_id=str(inv.id),
                patient_name=inv.patient_name_snapshot,
                patient_email=inv.patient_email_snapshot,
                status=inv.status,
                expires_at=inv.expires_at,
                questions=questions,
                collect_prior_documents=collect_prior,
                is_dynamic=True,
                dynamic_max_questions=DYNAMIC_QUESTIONNAIRE_MAX_QUESTIONS,
                dynamic_answered_count=answered_dynamic,
                enable_clinical_intake=enable_intake,
                intake_completed=intake_done,
                intake_only=intake_only,
                intake_sections=intake_sections,
                specialty=specialty,
                consultation_reason=reason,
            )

        items = (
            self._db.query(QuestionnaireInvitationItem)
            .filter(QuestionnaireInvitationItem.invitation_id == inv.id)
            .order_by(QuestionnaireInvitationItem.sort_order.asc())
            .all()
        )
        return PublicInvitationViewResponse(
            invitation_id=str(inv.id),
            patient_name=inv.patient_name_snapshot,
            patient_email=inv.patient_email_snapshot,
            status=inv.status,
            expires_at=inv.expires_at,
            collect_prior_documents=collect_prior,
            is_dynamic=False,
            dynamic_max_questions=DYNAMIC_QUESTIONNAIRE_MAX_QUESTIONS,
            dynamic_answered_count=0,
            enable_clinical_intake=enable_intake,
            intake_completed=intake_done,
            intake_only=intake_only,
            intake_sections=intake_sections,
            specialty=specialty,
            consultation_reason=reason,
            questions=[
                {
                    "item_id": str(i.id),
                    "question_text": i.question_text_snapshot,
                    "response_type": i.response_type_snapshot,
                    "options": list(i.options_snapshot) if i.options_snapshot else None,
                    "help_text": i.help_text_snapshot,
                    "is_required": bool(i.is_required_snapshot),
                    "specialty_name": i.specialty_name_snapshot,
                    "template_name": i.template_name_snapshot,
                }
                for i in items
            ],
        )

    def submit_public_invitation(
        self, raw_token: str, payload: PublicInvitationSubmitRequest
    ) -> tuple[PublicInvitationSubmitResponse, QuestionnaireInvitation]:
        inv = self._get_invitation_for_public_token(raw_token)
        inv = self._mark_expired_if_needed(inv)
        if inv.status == "completed":
            raise HTTPException(
                status_code=409, detail="Este cuestionario ya fue completado"
            )
        if inv.status != "pending":
            raise HTTPException(status_code=400, detail="Invitación no disponible")
        if bool(getattr(inv, "enable_clinical_intake", False)) and not inv.intake_completed_at:
            raise HTTPException(
                status_code=400,
                detail="Completa primero tu ficha clínica antes del cuestionario",
            )
        if bool(getattr(inv, "is_dynamic", False)):
            raise HTTPException(
                status_code=400,
                detail="Este cuestionario es dinámico; usa el flujo pregunta a pregunta",
            )

        items = (
            self._db.query(QuestionnaireInvitationItem)
            .filter(QuestionnaireInvitationItem.invitation_id == inv.id)
            .all()
        )
        item_by_id = {str(i.id): i for i in items}
        required_item_ids = {str(i.id) for i in items if i.is_required_snapshot}

        answer_by_item = {}
        for answer in payload.answers:
            if answer.item_id in item_by_id:
                answer_by_item[answer.item_id] = answer.answer

        missing_required = [
            iid
            for iid in required_item_ids
            if iid not in answer_by_item or answer_by_item[iid] in (None, "", [], {})
        ]
        if missing_required:
            raise HTTPException(
                status_code=400, detail="Faltan respuestas obligatorias"
            )

        for item_id, answer in answer_by_item.items():
            item_uuid = uuid.UUID(item_id)
            existing = (
                self._db.query(QuestionnaireInvitationAnswer)
                .filter(QuestionnaireInvitationAnswer.invitation_item_id == item_uuid)
                .first()
            )
            if existing:
                existing.answer_json = {"value": answer}
            else:
                self._db.add(
                    QuestionnaireInvitationAnswer(
                        invitation_item_id=item_uuid,
                        answer_json={"value": answer},
                    )
                )

        now = datetime.now(timezone.utc)
        inv.status = "completed"
        inv.used_at = now
        inv.completed_at = now
        self._db.commit()
        self._db.refresh(inv)

        return (
            PublicInvitationSubmitResponse(
                invitation_id=str(inv.id),
                status=inv.status,
                completed_at=inv.completed_at or now,
                collect_prior_documents=bool(
                    getattr(inv, "collect_prior_documents", False)
                ),
            ),
            inv,
        )

    def get_clinical_intake_detail_for_doctor(
        self,
        doctor_id: uuid.UUID,
        patient_id: uuid.UUID,
        invitation_id: uuid.UUID,
    ):
        from app.dto.clinical_intake_dto import (
            ClinicalIntakeDetailResponse,
            ClinicalIntakeFieldDetail,
            ClinicalIntakeSectionDetail,
        )
        from app.services.medical.intake_sections import (
            build_clinical_intake_detail_sections,
        )

        inv = (
            self._db.query(QuestionnaireInvitation)
            .filter(
                QuestionnaireInvitation.id == invitation_id,
                QuestionnaireInvitation.doctor_id == doctor_id,
                QuestionnaireInvitation.patient_id == patient_id,
            )
            .first()
        )
        if not inv:
            raise HTTPException(status_code=404, detail="Invitación no encontrada")
        if not inv.intake_completed_at:
            raise HTTPException(
                status_code=404, detail="La ficha clínica aún no está completada"
            )
        ctx = inv.intake_context if isinstance(inv.intake_context, dict) else {}
        saved = (
            inv.intake_responses if isinstance(inv.intake_responses, dict) else {}
        )
        sections_raw = build_clinical_intake_detail_sections(ctx, saved)
        sections = [
            ClinicalIntakeSectionDetail(
                id=s["id"],
                title=s["title"],
                subtitle=s.get("subtitle"),
                fields=[
                    ClinicalIntakeFieldDetail(
                        key=f["key"],
                        label=f["label"],
                        value=f["value"],
                    )
                    for f in s.get("fields") or []
                ],
            )
            for s in sections_raw
        ]
        return ClinicalIntakeDetailResponse(
            invitation_id=str(inv.id),
            patient_id=str(inv.patient_id),
            completed_at=inv.intake_completed_at,
            sections=sections,
        )

    def list_patient_completed_response_rows(
        self, patient_id: uuid.UUID, doctor_id: uuid.UUID
    ):
        return (
            self._db.query(
                QuestionnaireInvitationItem.question_text_snapshot.label(
                    "question_text"
                ),
                QuestionnaireInvitationAnswer.answer_json.label("answer_value"),
                QuestionnaireInvitationAnswer.answered_at,
            )
            .select_from(QuestionnaireInvitation)
            .join(
                QuestionnaireInvitationItem,
                QuestionnaireInvitationItem.invitation_id == QuestionnaireInvitation.id,
            )
            .join(
                QuestionnaireInvitationAnswer,
                QuestionnaireInvitationAnswer.invitation_item_id
                == QuestionnaireInvitationItem.id,
            )
            .filter(QuestionnaireInvitation.patient_id == patient_id)
            .filter(QuestionnaireInvitation.doctor_id == doctor_id)
            .filter(QuestionnaireInvitation.status == "completed")
            .order_by(QuestionnaireInvitationAnswer.answered_at.desc())
            .all()
        )
