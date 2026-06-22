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
    IntakeSectionView,
    InvitationQuestionView,
    PublicIntakeSectionSubmitResponse,
    PublicInvitationSubmitRequest,
    PublicInvitationSubmitResponse,
    PublicInvitationViewResponse,
    PendingQuestionnaireInvitationView,
    DoctorInvitationQuestionsResponse,
    DoctorInvitationSubmitResponse,
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

    @staticmethod
    def _template_ids_from_payload(data) -> List[uuid.UUID]:
        raw = getattr(data, "template_ids", None) or []
        ids: List[uuid.UUID] = []
        for item in raw:
            uid = _as_uuid(str(item))
            if uid is not None:
                ids.append(uid)
        return ids

    def _build_snapshot_questions(
        self,
        doctor_id: uuid.UUID,
        template_ids: List[uuid.UUID],
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

        if template_ids and not rows:
            raise HTTPException(
                status_code=400,
                detail="La plantilla seleccionada no tiene preguntas activas",
            )
        return rows

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
            template_name=item.template_name_snapshot,
        )

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
        template_ids = getattr(data, "template_ids", None) or []
        if template_ids:
            return False
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
        return self._invitation_item_count(inv.id) == 0

    def _apply_clinical_intake_to_invitation(
        self, invitation: QuestionnaireInvitation, data
    ) -> None:
        enable = self._enable_clinical_intake_from_payload(data)
        invitation.enable_clinical_intake = enable
        invitation.intake_context = (
            self._intake_context_from_payload(data) if enable else None
        )
        invitation.intake_responses = {} if enable else None

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
    ) -> tuple[PublicIntakeSectionSubmitResponse, Optional[QuestionnaireInvitation]]:
        inv = self._get_invitation_for_public_token(raw_token)
        return self._save_intake_section_for_invitation(inv, section_id, answers)

    def save_doctor_intake_section(
        self,
        doctor_id: uuid.UUID,
        invitation_id: uuid.UUID,
        section_id: str,
        answers: dict,
    ) -> PublicIntakeSectionSubmitResponse:
        inv = self._get_doctor_invitation(doctor_id, invitation_id)
        if inv.status != "pending":
            raise HTTPException(
                status_code=400, detail="Esta invitación ya no está disponible"
            )
        response, _ = self._save_intake_section_for_invitation(
            inv, section_id, answers
        )
        return response

    def _save_intake_section_for_invitation(
        self,
        inv: QuestionnaireInvitation,
        section_id: str,
        answers: dict,
    ) -> tuple[PublicIntakeSectionSubmitResponse, Optional[QuestionnaireInvitation]]:
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
        has_questions = self._invitation_item_count(inv.id) > 0
        collect_prior = bool(getattr(inv, "collect_prior_documents", False))
        if intake_is_complete(sections_raw, merged):
            inv.intake_completed_at = datetime.now(timezone.utc)
            if not has_questions and not collect_prior:
                now = datetime.now(timezone.utc)
                inv.status = "completed"
                inv.used_at = now
                inv.completed_at = now
        self._db.commit()
        self._db.refresh(inv)
        completed = inv.intake_completed_at is not None
        return (
            PublicIntakeSectionSubmitResponse(
                intake_completed=completed,
                intake_sections=sections,
                intake_only=intake_only,
                collect_prior_documents=bool(
                    getattr(inv, "collect_prior_documents", False)
                ),
            ),
            inv if intake_only and completed and not collect_prior and not has_questions else None,
        )

    def _resolve_collect_prior_documents(self, data) -> bool:
        return bool(getattr(data, "collect_prior_documents", False))

    def _invitation_has_pending_steps(self, inv: QuestionnaireInvitation) -> bool:
        if bool(getattr(inv, "enable_clinical_intake", False)) and not inv.intake_completed_at:
            return True
        if (
            self._invitation_item_count(inv.id) > 0
            and not self._questionnaire_is_complete(inv)
        ):
            return True
        return False

    def _questionnaire_is_complete(self, inv: QuestionnaireInvitation) -> bool:
        if getattr(inv, "questionnaire_completed_at", None) is not None:
            return True
        total = self._invitation_item_count(inv.id)
        if total == 0:
            return False
        answered = (
            self._db.query(func.count(QuestionnaireInvitationAnswer.id))
            .join(
                QuestionnaireInvitationItem,
                QuestionnaireInvitationItem.id
                == QuestionnaireInvitationAnswer.invitation_item_id,
            )
            .filter(QuestionnaireInvitationItem.invitation_id == inv.id)
            .scalar()
            or 0
        )
        return int(answered) >= total

    def _questionnaire_name_for_invitation(
        self, invitation_id: uuid.UUID
    ) -> str:
        row = (
            self._db.query(QuestionnaireInvitationItem.template_name_snapshot)
            .filter(QuestionnaireInvitationItem.invitation_id == invitation_id)
            .order_by(QuestionnaireInvitationItem.sort_order.asc())
            .first()
        )
        name = (row[0] if row else "") or ""
        return name.strip() or "Cuestionario"

    def _invitation_display_label(self, inv: QuestionnaireInvitation) -> str:
        parts: List[str] = []
        has_questions = self._invitation_item_count(inv.id) > 0
        if bool(getattr(inv, "enable_clinical_intake", False)):
            parts.append("Ficha clínica")
        if has_questions:
            name = self._questionnaire_name_for_invitation(inv.id)
            parts.append(name if name != "Cuestionario" else "Cuestionario")
        if bool(getattr(inv, "collect_prior_documents", False)):
            parts.append("Documentos previos")
        return " · ".join(parts) if parts else "Invitación pendiente"

    def _get_doctor_invitation(
        self, doctor_id: uuid.UUID, invitation_id: uuid.UUID
    ) -> QuestionnaireInvitation:
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
        return self._mark_expired_if_needed(inv)

    def _build_invitation_workflow_view(
        self, inv: QuestionnaireInvitation
    ) -> PublicInvitationViewResponse:
        enable_intake, intake_done, intake_sections, specialty, reason = (
            self._intake_meta_for_invitation(inv)
        )
        intake_only = self._is_intake_only_invitation(inv)
        collect_prior = bool(getattr(inv, "collect_prior_documents", False))
        has_questionnaire = self._invitation_item_count(inv.id) > 0
        questionnaire_completed = self._questionnaire_is_complete(inv)
        questionnaire_answered_by = getattr(inv, "questionnaire_answered_by", None)

        questions: List[InvitationQuestionView] = []
        if (
            inv.status == "pending"
            and has_questionnaire
            and not questionnaire_completed
        ):
            items = (
                self._db.query(QuestionnaireInvitationItem)
                .filter(QuestionnaireInvitationItem.invitation_id == inv.id)
                .order_by(QuestionnaireInvitationItem.sort_order.asc())
                .all()
            )
            questions = [self._invitation_item_to_view(i) for i in items]

        base_kwargs = dict(
            invitation_id=str(inv.id),
            patient_name=inv.patient_name_snapshot,
            patient_email=inv.patient_email_snapshot,
            status=inv.status,
            expires_at=inv.expires_at,
            questions=questions,
            collect_prior_documents=collect_prior,
            is_dynamic=False,
            dynamic_max_questions=0,
            dynamic_answered_count=0,
            enable_clinical_intake=enable_intake,
            intake_completed=intake_done,
            intake_only=intake_only,
            intake_sections=intake_sections,
            specialty=specialty,
            consultation_reason=reason,
            has_questionnaire=has_questionnaire,
            questionnaire_completed=questionnaire_completed,
            questionnaire_answered_by=questionnaire_answered_by,
        )

        if inv.status != "pending":
            return PublicInvitationViewResponse(**base_kwargs)

        if enable_intake and not intake_done:
            return PublicInvitationViewResponse(
                **{
                    **base_kwargs,
                    "enable_clinical_intake": True,
                    "intake_completed": False,
                }
            )

        return PublicInvitationViewResponse(**base_kwargs)

    def _persist_questionnaire_answers(
        self,
        inv: QuestionnaireInvitation,
        payload: PublicInvitationSubmitRequest,
        *,
        answered_by: str,
    ) -> datetime:
        items = (
            self._db.query(QuestionnaireInvitationItem)
            .filter(QuestionnaireInvitationItem.invitation_id == inv.id)
            .all()
        )
        if not items:
            raise HTTPException(
                status_code=400, detail="Esta invitación no incluye cuestionario"
            )

        item_by_id = {str(i.id): i for i in items}
        required_item_ids = {str(i.id) for i in items if i.is_required_snapshot}

        answer_by_item: dict[str, Any] = {}
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
        inv.questionnaire_completed_at = now
        inv.questionnaire_answered_by = answered_by
        inv.used_at = inv.used_at or now
        return now

    def complete_public_invitation(
        self, raw_token: str
    ) -> QuestionnaireInvitation:
        inv = self._get_invitation_for_public_token(raw_token)
        inv = self._mark_expired_if_needed(inv)
        if inv.status == "completed":
            return inv
        if inv.status != "pending":
            raise HTTPException(status_code=400, detail="Invitación no disponible")
        if self._invitation_has_pending_steps(inv):
            raise HTTPException(
                status_code=400,
                detail="Aún hay pasos pendientes en esta invitación",
            )
        now = datetime.now(timezone.utc)
        inv.status = "completed"
        inv.used_at = now
        inv.completed_at = now
        self._db.commit()
        self._db.refresh(inv)
        return inv

    def create_invitation_batch(
        self, doctor_id: uuid.UUID, data: QuestionnaireSendInvitationRequest
    ) -> tuple[QuestionnaireInvitationSummaryResponse, str]:
        enable_intake = self._enable_clinical_intake_from_payload(data)
        template_ids = self._template_ids_from_payload(data)
        collect_docs = self._resolve_collect_prior_documents(data)

        if not enable_intake and not collect_docs and not template_ids:
            raise HTTPException(
                status_code=400,
                detail="Activa al menos una opción: ficha clínica, documentos o cuestionario",
            )

        patient_id = _as_uuid(data.patient_id)
        if patient_id is None:
            raise HTTPException(status_code=400, detail="patient_id inválido")
        patient = self._load_patient_owned_by_doctor(doctor_id, patient_id)

        snapshot_rows: List[dict] = []
        if template_ids:
            snapshot_rows = self._build_snapshot_questions(doctor_id, template_ids)

        expires_at = datetime.now(timezone.utc) + timedelta(hours=24)

        invitation = QuestionnaireInvitation(
            doctor_id=doctor_id,
            patient_id=patient.id,
            patient_email_snapshot=patient.email,
            patient_name_snapshot=patient.name,
            token_hash="__pending__",
            status="pending",
            expires_at=expires_at,
            collect_prior_documents=self._resolve_collect_prior_documents(data),
        )
        self._apply_clinical_intake_to_invitation(invitation, data)
        self._db.add(invitation)
        self._db.flush()

        for idx, row in enumerate(snapshot_rows):
            self._db.add(
                QuestionnaireInvitationItem(
                    invitation_id=invitation.id,
                    question_id=row["question_id"],
                    question_text_snapshot=row["question_text"],
                    response_type_snapshot=row["response_type"],
                    options_snapshot=row["options"],
                    help_text_snapshot=row["help_text"],
                    is_required_snapshot=row["is_required"],
                    specialty_name_snapshot=row.get("specialty_name"),
                    template_name_snapshot=row.get("template_name"),
                    sort_order=idx,
                )
            )

        raw_token = self._generate_invitation_secret_token()
        invitation.token_hash = self._hash_token(raw_token)
        self._db.commit()
        self._db.refresh(invitation)
        return self._invitation_to_summary(invitation, len(snapshot_rows)), raw_token

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
        return self._build_invitation_workflow_view(inv)

    def get_invitation_workflow_for_doctor(
        self, doctor_id: uuid.UUID, invitation_id: uuid.UUID
    ) -> PublicInvitationViewResponse:
        inv = self._get_doctor_invitation(doctor_id, invitation_id)
        return self._build_invitation_workflow_view(inv)

    def finish_doctor_invitation(
        self, doctor_id: uuid.UUID, invitation_id: uuid.UUID
    ) -> dict:
        inv = self._get_doctor_invitation(doctor_id, invitation_id)
        if inv.status == "completed":
            return {"invitation_id": str(inv.id), "status": inv.status}
        if inv.status != "pending":
            raise HTTPException(status_code=400, detail="Invitación no disponible")
        if self._invitation_has_pending_steps(inv):
            raise HTTPException(
                status_code=400,
                detail="Aún hay pasos pendientes en esta invitación",
            )
        now = datetime.now(timezone.utc)
        inv.status = "completed"
        inv.used_at = inv.used_at or now
        inv.completed_at = now
        self._db.commit()
        self._db.refresh(inv)
        return {"invitation_id": str(inv.id), "status": inv.status}

    def submit_public_invitation(
        self, raw_token: str, payload: PublicInvitationSubmitRequest
    ) -> tuple[PublicInvitationSubmitResponse, QuestionnaireInvitation]:
        inv = self._get_invitation_for_public_token(raw_token)
        inv = self._mark_expired_if_needed(inv)
        if self._questionnaire_is_complete(inv):
            if getattr(inv, "questionnaire_answered_by", None) == "doctor":
                raise HTTPException(
                    status_code=409,
                    detail="Este cuestionario ya fue contestado por tu médico",
                )
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

        now = self._persist_questionnaire_answers(
            inv, payload, answered_by="patient"
        )
        inv.status = "completed"
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
                QuestionnaireInvitation.id.label("invitation_id"),
                QuestionnaireInvitationItem.template_name_snapshot.label(
                    "questionnaire_name"
                ),
                QuestionnaireInvitationItem.question_text_snapshot.label(
                    "question_text"
                ),
                QuestionnaireInvitationAnswer.answer_json.label("answer_value"),
                QuestionnaireInvitationAnswer.answered_at,
                QuestionnaireInvitation.questionnaire_answered_by.label("answered_by"),
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
            .filter(
                or_(
                    QuestionnaireInvitation.questionnaire_completed_at.isnot(None),
                    QuestionnaireInvitation.status == "completed",
                )
            )
            .order_by(QuestionnaireInvitationAnswer.answered_at.desc())
            .all()
        )

    def list_patient_pending_questionnaire_invitations(
        self, patient_id: uuid.UUID, doctor_id: uuid.UUID
    ) -> List[PendingQuestionnaireInvitationView]:
        rows = (
            self._db.query(QuestionnaireInvitation)
            .filter(
                QuestionnaireInvitation.patient_id == patient_id,
                QuestionnaireInvitation.doctor_id == doctor_id,
                QuestionnaireInvitation.status == "pending",
            )
            .order_by(QuestionnaireInvitation.created_at.desc())
            .all()
        )
        pending: List[PendingQuestionnaireInvitationView] = []
        for inv in rows:
            inv = self._mark_expired_if_needed(inv)
            if inv.status != "pending":
                continue
            total = self._invitation_item_count(inv.id)
            enable_intake = bool(getattr(inv, "enable_clinical_intake", False))
            pending.append(
                PendingQuestionnaireInvitationView(
                    id=str(inv.id),
                    questionnaire_name=self._invitation_display_label(inv),
                    status=inv.status,
                    created_at=inv.created_at,
                    expires_at=inv.expires_at,
                    total_questions=total,
                    enable_clinical_intake=enable_intake,
                    collect_prior_documents=bool(
                        getattr(inv, "collect_prior_documents", False)
                    ),
                    intake_completed=inv.intake_completed_at is not None,
                    has_questionnaire=total > 0,
                    questionnaire_completed=(
                        self._questionnaire_is_complete(inv) if total > 0 else False
                    ),
                    intake_only=self._is_intake_only_invitation(inv),
                )
            )
        return pending

    def get_invitation_questions_for_doctor(
        self, doctor_id: uuid.UUID, invitation_id: uuid.UUID
    ) -> DoctorInvitationQuestionsResponse:
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
        if inv.status != "pending":
            raise HTTPException(
                status_code=400, detail="Esta invitación ya no está pendiente"
            )
        if self._questionnaire_is_complete(inv):
            raise HTTPException(
                status_code=409, detail="Este cuestionario ya fue contestado"
            )
        items = (
            self._db.query(QuestionnaireInvitationItem)
            .filter(QuestionnaireInvitationItem.invitation_id == inv.id)
            .order_by(QuestionnaireInvitationItem.sort_order.asc())
            .all()
        )
        if not items:
            raise HTTPException(
                status_code=400, detail="Esta invitación no incluye cuestionario"
            )
        return DoctorInvitationQuestionsResponse(
            invitation_id=str(inv.id),
            questionnaire_name=self._questionnaire_name_for_invitation(inv.id),
            patient_name=inv.patient_name_snapshot,
            questions=[self._invitation_item_to_view(i) for i in items],
        )

    def submit_doctor_invitation(
        self,
        doctor_id: uuid.UUID,
        invitation_id: uuid.UUID,
        payload: PublicInvitationSubmitRequest,
    ) -> DoctorInvitationSubmitResponse:
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
        if inv.status != "pending":
            raise HTTPException(
                status_code=400, detail="Esta invitación ya no está pendiente"
            )
        if self._questionnaire_is_complete(inv):
            raise HTTPException(
                status_code=409, detail="Este cuestionario ya fue contestado"
            )

        now = self._persist_questionnaire_answers(
            inv, payload, answered_by="doctor"
        )

        intake_pending = bool(
            getattr(inv, "enable_clinical_intake", False)
        ) and not inv.intake_completed_at
        docs_step = bool(getattr(inv, "collect_prior_documents", False))
        if intake_pending or docs_step:
            inv.status = "pending"
        else:
            inv.status = "completed"
            inv.completed_at = now

        self._db.commit()
        self._db.refresh(inv)

        return DoctorInvitationSubmitResponse(
            invitation_id=str(inv.id),
            status=inv.status,
            questionnaire_answered_by="doctor",
            questionnaire_completed_at=inv.questionnaire_completed_at or now,
        )
