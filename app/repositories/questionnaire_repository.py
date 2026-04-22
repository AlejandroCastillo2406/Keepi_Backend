"""Repositorio de cuestionarios de salud.

Responsable de todas las queries relacionadas a preguntas/especialidades/plantillas/overrides.
Aplica overrides del doctor al materializar las preguntas.
"""

from __future__ import annotations

import uuid
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

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


def _as_uuid(value: Optional[str]) -> Optional[uuid.UUID]:
    if value is None or value == "":
        return None
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ID inválido") from exc


def _coalesce(override_val: Optional[bool], default_val: bool) -> bool:
    return default_val if override_val is None else bool(override_val)


def _effective_fields(q: Question, override: Optional[DoctorQuestionOverride]) -> dict[str, bool]:
    return {
        "is_active": _coalesce(
            override.is_active if override else None, bool(q.is_active_default)
        ),
        "is_required": _coalesce(
            override.is_required if override else None, bool(q.is_required_default)
        ),
        "show_in_history": _coalesce(
            override.show_in_history if override else None, bool(q.show_in_history_default)
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

    # ────── Specialties ──────

    def list_specialties(self) -> List[Specialty]:
        return (
            self._db.query(Specialty)
            .order_by(Specialty.sort_order.asc(), Specialty.name.asc())
            .all()
        )

    def list_specialties_with_counts(self, doctor_id: uuid.UUID) -> List[SpecialtySummary]:
        specialties = self.list_specialties()
        summaries: List[SpecialtySummary] = []
        for spec in specialties:
            questions = self._fetch_visible_questions(
                doctor_id, specialty_id=spec.id, only_globals=False
            )
            total = len(questions)
            active = sum(1 for q, ov in questions if _effective_fields(q, ov)["is_active"])
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

    # ────── Questions ──────

    def _fetch_visible_questions(
        self,
        doctor_id: uuid.UUID,
        *,
        specialty_id: Optional[uuid.UUID] = None,
        only_globals: bool = False,
    ) -> List[tuple[Question, Optional[DoctorQuestionOverride]]]:
        """Retorna preguntas visibles al doctor: system + propias.

        - `specialty_id`: si se envía, filtra esa especialidad.
        - `only_globals`: si es True, filtra `specialty_id IS NULL` y ignora `specialty_id`.
        """
        ownership_filter = or_(
            Question.origin == "system",
            Question.owner_user_id == doctor_id,
        )

        q = self._db.query(Question).filter(ownership_filter)
        if only_globals:
            q = q.filter(Question.specialty_id.is_(None))
        elif specialty_id is not None:
            q = q.filter(Question.specialty_id == specialty_id)

        questions = q.order_by(Question.sort_order.asc(), Question.created_at.asc()).all()

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
        # precargar specialties para pintar nombre
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

    def get_question_dto(self, doctor_id: uuid.UUID, question_id: uuid.UUID) -> QuestionResponse:
        q = self._db.query(Question).filter(Question.id == question_id).first()
        if not q:
            raise HTTPException(status_code=404, detail="Pregunta no encontrada")
        # Visibilidad
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

        # siguiente sort_order dentro del ámbito del doctor
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
                raise HTTPException(status_code=400, detail="Tipo de respuesta inválido")
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

        # validación de opciones según tipo
        if q.response_type in ("single_choice", "multi_choice"):
            if not q.options or len(q.options) < 2:
                raise HTTPException(
                    status_code=400,
                    detail="Debe incluir al menos 2 opciones para este tipo de respuesta",
                )

        self._db.commit()
        self._db.refresh(q)
        return self.get_question_dto(doctor_id, q.id)

    def delete_custom_question(self, doctor_id: uuid.UUID, question_id: uuid.UUID) -> None:
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

    # ────── Overrides ──────

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

        # Preguntas propias: el toggle se guarda en la pregunta misma (default).
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

    # ────── Templates ──────

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
            .order_by(TemplateQuestion.sort_order.asc(), TemplateQuestion.created_at.asc())
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
                for s in self._db.query(Specialty).filter(Specialty.id.in_(spec_ids)).all():
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
        # Unique por (doctor, name)
        exists = (
            self._db.query(Template)
            .filter(Template.doctor_id == doctor_id, Template.name == data.name.strip())
            .first()
        )
        if exists:
            raise HTTPException(status_code=409, detail="Ya tienes una plantilla con ese nombre")

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

        # validar que cada pregunta sea visible al doctor (system o propia)
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

        # reemplazo completo
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
