"""Lógica del cuestionario de salud: catálogo, preferencias, plantillas y envíos tipados."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.roles import ROLE_PATIENT
from app.models.health_questionnaire import (
    DoctorQuestionCreateRequest,
    DoctorQuestionListResponse,
    DoctorQuestionnaireSettingsPatchRequest,
    DoctorQuestionnaireSettingsResponse,
    DoctorQuestionOut,
    DoctorQuestionReorderRequest,
    DoctorQuestionSettingRow,
    DoctorQuestionUpdateRequest,
    HealthQuestionBank,
    HealthQuestionDoctorVisibility,
    HealthQuestionnaireAnswer,
    HealthQuestionnaireSubmission,
    HealthQuestionnaireTemplate,
    HealthQuestionnaireTemplateAssignment,
    HealthQuestionnaireTemplateQuestion,
    HealthSpecialty,
    PatientHealthCompletion,
    QuestionnaireForPatientResponse,
    QuestionnaireQuestionOut,
    QuestionnaireSectionOut,
    QuestionnaireSubmitRequest,
    SpecialtiesListResponse,
    SpecialtyOut,
    TemplateAssignRequest,
    TemplateCreateRequest,
    TemplateDetailOut,
    TemplateListResponse,
    TemplateOut,
    TemplateQuestionOut,
    TemplateUpdateRequest,
)
from app.models.user import User, UserResponse
from app.services.notificaciones.user_notify import notify_user_push_and_db

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

VALID_QUESTION_TYPES = {
    "single_choice",
    "multi_choice",
    "yes_no",
    "numeric",
    "short_text",
    "long_text",
}

SPECIALTIES_SEED: List[Tuple[str, str, str, str, int]] = [
    ("medicina_general", "Medicina general", "Preguntas generales de salud y antecedentes.", "stethoscope", 10),
    ("cardiologia", "Cardiología", "Enfocadas en salud cardiovascular.", "heart", 20),
    ("neumologia", "Neumología", "Evaluación respiratoria y pulmonar.", "lungs", 30),
    ("ginecologia", "Ginecología", "Salud femenina y reproductiva.", "female", 40),
    ("endocrinologia", "Endocrinología", "Metabolismo, hormonas y diabetes.", "hormone", 50),
    ("neurologia", "Neurología", "Sistema nervioso y trastornos neurológicos.", "brain", 60),
    ("oftalmologia", "Oftalmología", "Salud visual y ocular.", "eye", 70),
]

# Preguntas seed de Keepi. `opts` es la lista de opciones si aplica al tipo.
_SeedQ = Tuple[Optional[str], str, str, Optional[List[str]], int]  # (specialty_code, prompt, type, options, order)
QUESTIONS_SEED: List[_SeedQ] = [
    # --- Globales (specialty_code = None) ---
    (None, "¿Cuál es el motivo principal de tu consulta o seguimiento?", "long_text", None, 10),
    (None, "¿Tomas medicamentos de forma regular?", "yes_no", None, 20),
    (None, "¿Tienes alergias conocidas a medicamentos, alimentos u otras sustancias?", "short_text", None, 30),
    # --- Medicina general ---
    ("medicina_general", "¿Ha tenido fiebre, pérdida de peso no intencionada o fatiga persistente en las últimas semanas?", "yes_no", None, 110),
    ("medicina_general", "¿Cómo calificarías tu nivel de estrés en las últimas semanas?", "single_choice", ["Bajo", "Moderado", "Alto", "Muy alto"], 120),
    # --- Cardiología ---
    ("cardiologia", "¿Ha sentido dolor u opresión en el pecho, palpitaciones o mareos frecuentes recientemente?", "yes_no", None, 210),
    ("cardiologia", "¿Tiene antecedentes familiares de enfermedad cardiovascular (infarto, ACV antes de los 55 años)?", "yes_no", None, 220),
    # --- Neumología ---
    ("neumologia", "¿Fumas o has fumado en el último año?", "single_choice", ["Nunca", "Ex fumador", "Ocasional", "Diario"], 310),
    ("neumologia", "¿Tienes tos persistente, falta de aire o sibilancias?", "yes_no", None, 320),
    # --- Ginecología ---
    ("ginecologia", "¿Hay posibilidad de embarazo actual o estás en periodo de lactancia?", "single_choice", ["No", "Posible embarazo", "Lactancia"], 410),
    ("ginecologia", "Fecha aproximada de tu última menstruación", "short_text", None, 420),
    # --- Endocrinología ---
    ("endocrinologia", "¿Le han diagnosticado diabetes, resistencia a la insulina o alteraciones de la tiroides?", "yes_no", None, 510),
    ("endocrinologia", "¿Ha medido glucosa en ayunas o HbA1c recientemente? Indica valores si los conoces.", "short_text", None, 520),
    # --- Neurología ---
    ("neurologia", "¿Has tenido dolores de cabeza frecuentes, mareos o pérdidas de memoria?", "yes_no", None, 610),
    ("neurologia", "¿Has tenido episodios de pérdida de conciencia o crisis convulsivas?", "yes_no", None, 620),
    # --- Oftalmología ---
    ("oftalmologia", "¿Usas lentes o lentes de contacto?", "single_choice", ["No", "Lentes", "Lentes de contacto", "Ambos"], 710),
    ("oftalmologia", "¿Has notado cambios recientes en tu visión?", "yes_no", None, 720),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _specialty_label(db: Session, code: Optional[str]) -> Optional[str]:
    if not code:
        return None
    sp = db.query(HealthSpecialty).filter(HealthSpecialty.code == code).first()
    return sp.label if sp else None


# ---------------------------------------------------------------------------
# Migración ligera + seed
# ---------------------------------------------------------------------------


_MIGRATION_STATEMENTS: List[str] = [
    # Nuevas columnas en HealthQuestionBank
    "ALTER TABLE health_question_bank ADD COLUMN IF NOT EXISTS owner_doctor_user_id UUID",
    "ALTER TABLE health_question_bank ADD COLUMN IF NOT EXISTS question_type VARCHAR(32) NOT NULL DEFAULT 'short_text'",
    "ALTER TABLE health_question_bank ADD COLUMN IF NOT EXISTS options JSONB",
    "ALTER TABLE health_question_bank ADD COLUMN IF NOT EXISTS is_required BOOLEAN NOT NULL DEFAULT TRUE",
    "ALTER TABLE health_question_bank ADD COLUMN IF NOT EXISTS show_in_history BOOLEAN NOT NULL DEFAULT TRUE",
    "ALTER TABLE health_question_bank ADD COLUMN IF NOT EXISTS help_text TEXT",
    "ALTER TABLE health_question_bank ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()",
    "CREATE INDEX IF NOT EXISTS ix_hqb_owner_doctor ON health_question_bank (owner_doctor_user_id)",
    # Nuevas columnas en answers
    "ALTER TABLE health_questionnaire_answers ADD COLUMN IF NOT EXISTS answer_value JSONB",
    # template_id en submissions
    "ALTER TABLE health_questionnaire_submissions ADD COLUMN IF NOT EXISTS template_id UUID",
]


def _run_light_migrations(db: Session) -> None:
    """Aplica `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` para las columnas nuevas."""
    for stmt in _MIGRATION_STATEMENTS:
        try:
            db.execute(text(stmt))
        except Exception as e:  # tabla aún no existe en primer boot, lo creará metadata.create_all
            logger.debug("Migración ligera omitida [%s]: %s", stmt, e)
    try:
        db.commit()
    except Exception:
        db.rollback()


def seed_catalog_if_empty(db: Session) -> None:
    """Corre migración ligera y siembra especialidades + preguntas si faltan."""
    _run_light_migrations(db)

    if db.query(HealthSpecialty).count() == 0:
        for code, label, desc, icon, order in SPECIALTIES_SEED:
            db.add(
                HealthSpecialty(
                    code=code,
                    label=label,
                    description=desc,
                    icon_key=icon,
                    sort_order=order,
                )
            )
        db.commit()
        logger.info("Seed: %s especialidades insertadas", len(SPECIALTIES_SEED))

    if db.query(HealthQuestionBank).count() == 0:
        for spec_code, prompt, qtype, opts, order in QUESTIONS_SEED:
            db.add(
                HealthQuestionBank(
                    section=("specialty" if spec_code else "general"),
                    specialty_code=spec_code,
                    specialty_label=_specialty_label(db, spec_code),
                    prompt=prompt,
                    sort_order=order,
                    is_active=True,
                    source="seed",
                    owner_doctor_user_id=None,
                    question_type=qtype,
                    options=opts,
                    is_required=True,
                    show_in_history=True,
                )
            )
        db.commit()
        logger.info("Seed: %s preguntas de Keepi insertadas", len(QUESTIONS_SEED))


# ---------------------------------------------------------------------------
# Flags de usuario (auth / user_service)
# ---------------------------------------------------------------------------


def build_user_response_with_flags(db: Session, user: User) -> UserResponse:
    """UserResponse con bandera de cuestionario pendiente (paciente dado de alta por médico)."""
    seed_catalog_if_empty(db)
    pending = patient_must_complete_questionnaire(db, user)
    return UserResponse.from_orm(user, pending_health_questionnaire=pending)


def patient_must_complete_questionnaire(db: Session, user: User) -> bool:
    """Paciente creado por médico y aún sin primera respuesta."""
    if user.role is None or user.role.name != ROLE_PATIENT:
        return False
    if user.created_by_user_id is None:
        return False
    row = db.query(PatientHealthCompletion).filter(PatientHealthCompletion.patient_user_id == user.id).first()
    return row is None


# ---------------------------------------------------------------------------
# Visibilidad (legacy sobre preguntas de Keepi)
# ---------------------------------------------------------------------------


def _doctor_has_any_visibility_row(db: Session, doctor_id: UUID) -> bool:
    return (
        db.query(HealthQuestionDoctorVisibility)
        .filter(HealthQuestionDoctorVisibility.doctor_user_id == doctor_id)
        .count()
        > 0
    )


def _seed_question_visible_for_doctor(db: Session, doctor_id: UUID, q: HealthQuestionBank) -> bool:
    """Regla para preguntas de Keepi: por defecto **activas**; el doctor puede desactivarlas."""
    ov = (
        db.query(HealthQuestionDoctorVisibility)
        .filter(
            HealthQuestionDoctorVisibility.doctor_user_id == doctor_id,
            HealthQuestionDoctorVisibility.question_id == q.id,
        )
        .first()
    )
    if ov is None:
        return True
    return bool(ov.is_visible)


def _question_is_active_for_doctor(db: Session, doctor_id: UUID, q: HealthQuestionBank) -> bool:
    """True si la pregunta se mostrará a los pacientes del doctor."""
    if not q.is_active:
        return False
    if q.owner_doctor_user_id is not None:
        return q.owner_doctor_user_id == doctor_id
    # Pregunta de Keepi
    return _seed_question_visible_for_doctor(db, doctor_id, q)


# ---------------------------------------------------------------------------
# Cuestionario del paciente
# ---------------------------------------------------------------------------


def _question_out(q: HealthQuestionBank) -> QuestionnaireQuestionOut:
    return QuestionnaireQuestionOut(
        id=str(q.id),
        prompt=q.prompt,
        question_type=q.question_type or "short_text",  # type: ignore[arg-type]
        options=list(q.options) if q.options else None,
        is_required=bool(q.is_required),
        help_text=q.help_text,
    )


def _resolve_patient_template(db: Session, patient: User) -> Optional[HealthQuestionnaireTemplate]:
    row = (
        db.query(HealthQuestionnaireTemplateAssignment)
        .filter(HealthQuestionnaireTemplateAssignment.patient_user_id == patient.id)
        .order_by(HealthQuestionnaireTemplateAssignment.created_at.desc())
        .first()
    )
    if row is None:
        return None
    return db.query(HealthQuestionnaireTemplate).filter(HealthQuestionnaireTemplate.id == row.template_id).first()


def build_questionnaire_for_patient(db: Session, patient: User) -> QuestionnaireForPatientResponse:
    seed_catalog_if_empty(db)
    if patient.role is None or patient.role.name != ROLE_PATIENT:
        raise PermissionError("Solo pacientes")
    if patient.created_by_user_id is None:
        return QuestionnaireForPatientResponse(
            completed=True,
            message="No aplica cuestionario de alta por médico.",
            sections=[],
        )
    done = db.query(PatientHealthCompletion).filter(PatientHealthCompletion.patient_user_id == patient.id).first()
    if done is not None:
        return QuestionnaireForPatientResponse(completed=True, message="Ya completaste el cuestionario.", sections=[])

    doctor_id = patient.created_by_user_id
    template = _resolve_patient_template(db, patient)

    visible: List[HealthQuestionBank] = []
    template_id: Optional[str] = None
    template_name: Optional[str] = None

    if template is not None:
        template_id = str(template.id)
        template_name = template.name
        tq_rows = (
            db.query(HealthQuestionnaireTemplateQuestion)
            .filter(HealthQuestionnaireTemplateQuestion.template_id == template.id)
            .order_by(HealthQuestionnaireTemplateQuestion.sort_order.asc())
            .all()
        )
        q_ids = [tq.question_id for tq in tq_rows]
        if q_ids:
            q_by_id: Dict[UUID, HealthQuestionBank] = {
                q.id: q
                for q in db.query(HealthQuestionBank)
                .filter(HealthQuestionBank.id.in_(q_ids), HealthQuestionBank.is_active.is_(True))
                .all()
            }
            for tq in tq_rows:
                q = q_by_id.get(tq.question_id)
                if q is not None:
                    visible.append(q)
    else:
        # Sin plantilla asignada: el paciente ve todas las preguntas activas del doctor
        # (globales y de cualquier especialidad; la especialidad es solo organización interna).
        q_rows = (
            db.query(HealthQuestionBank)
            .filter(HealthQuestionBank.is_active.is_(True))
            .order_by(HealthQuestionBank.sort_order.asc(), HealthQuestionBank.id.asc())
            .all()
        )
        for q in q_rows:
            if not _question_is_active_for_doctor(db, doctor_id, q):
                continue
            visible.append(q)

    sections_map: Dict[Tuple[str, Optional[str]], List[HealthQuestionBank]] = defaultdict(list)
    for q in visible:
        key = (q.section, q.specialty_code or "")
        sections_map[key].append(q)

    sections: List[QuestionnaireSectionOut] = []
    for (section, spec_code), items in sorted(
        sections_map.items(),
        key=lambda kv: (min(x.sort_order for x in kv[1]), kv[0][0], kv[0][1] or ""),
    ):
        first = items[0]
        if section == "general":
            title = "Preguntas generales"
        else:
            title = f"Especialidad · {first.specialty_label or first.specialty_code or 'Clínica'}"
        sections.append(
            QuestionnaireSectionOut(
                title=title,
                section=section,  # type: ignore[arg-type]
                specialty_code=first.specialty_code,
                specialty_label=first.specialty_label,
                questions=[_question_out(x) for x in sorted(items, key=lambda z: z.sort_order)],
            )
        )

    return QuestionnaireForPatientResponse(
        completed=False,
        message=None if sections else "Tu médico aún no configuró preguntas para ti.",
        sections=sections,
        template_id=template_id,
        template_name=template_name,
    )


def _coerce_answer(q: HealthQuestionBank, raw_value: Any, raw_text: Optional[str]) -> Tuple[Any, str]:
    """Devuelve (answer_value, answer_text) validado segÃºn el tipo de la pregunta."""
    qtype = q.question_type or "short_text"
    value: Any = raw_value if raw_value is not None else raw_text
    text_repr: str = ""

    if qtype in ("short_text", "long_text"):
        s = "" if value is None else str(value).strip()
        if q.is_required and not s:
            raise ValueError(f"La pregunta '{q.prompt[:40]}…' es obligatoria")
        return s, s

    if qtype == "yes_no":
        s = str(value).strip().lower() if value is not None else ""
        if s in ("true", "si", "sí", "yes", "1"):
            return "si", "Sí"
        if s in ("false", "no", "0"):
            return "no", "No"
        if q.is_required:
            raise ValueError(f"La pregunta '{q.prompt[:40]}…' requiere Sí/No")
        return None, ""

    if qtype == "numeric":
        if value is None or value == "":
            if q.is_required:
                raise ValueError(f"La pregunta '{q.prompt[:40]}…' requiere un número")
            return None, ""
        try:
            n = float(value)
        except Exception:
            raise ValueError(f"Valor numérico inválido para '{q.prompt[:40]}…'")
        # Guardar como int si no tiene decimales
        if n.is_integer():
            n = int(n)
        return n, str(n)

    if qtype == "single_choice":
        opts = list(q.options or [])
        s = str(value).strip() if value is not None else ""
        if not s:
            if q.is_required:
                raise ValueError(f"La pregunta '{q.prompt[:40]}…' requiere una opción")
            return None, ""
        if opts and s not in opts:
            raise ValueError(f"Opción inválida para '{q.prompt[:40]}…'")
        return s, s

    if qtype == "multi_choice":
        opts = list(q.options or [])
        if isinstance(value, list):
            chosen = [str(x).strip() for x in value if str(x).strip()]
        elif isinstance(value, str):
            chosen = [p.strip() for p in value.split(",") if p.strip()]
        else:
            chosen = []
        if q.is_required and not chosen:
            raise ValueError(f"La pregunta '{q.prompt[:40]}…' requiere al menos una opción")
        if opts:
            bad = [c for c in chosen if c not in opts]
            if bad:
                raise ValueError(f"Opciones inválidas para '{q.prompt[:40]}…': {', '.join(bad)}")
        return chosen, ", ".join(chosen)

    raise ValueError(f"Tipo de pregunta no soportado: {qtype}")


def submit_questionnaire(db: Session, patient: User, body: QuestionnaireSubmitRequest) -> None:
    seed_catalog_if_empty(db)
    if patient.role is None or patient.role.name != ROLE_PATIENT:
        raise PermissionError("Solo pacientes")
    if patient.created_by_user_id is None:
        raise ValueError("Este flujo de cuestionario no aplica a tu cuenta.")
    existing = db.query(PatientHealthCompletion).filter(PatientHealthCompletion.patient_user_id == patient.id).first()
    if existing is not None:
        raise ValueError("Ya enviaste el cuestionario.")

    doctor_id = patient.created_by_user_id
    expected = build_questionnaire_for_patient(db, patient)
    if expected.completed or not expected.sections:
        raise ValueError("No hay preguntas pendientes o el cuestionario ya fue completado.")

    expected_questions: Dict[UUID, QuestionnaireQuestionOut] = {}
    for sec in expected.sections:
        for qo in sec.questions:
            expected_questions[UUID(qo.id)] = qo

    incoming: Dict[UUID, Tuple[Any, Optional[str]]] = {}
    for a in body.answers:
        try:
            qid = UUID(str(a.question_id))
        except Exception:
            raise ValueError(f"ID de pregunta inválido: {a.question_id}")
        incoming[qid] = (a.answer_value, a.answer_text)

    missing = [qid for qid in expected_questions.keys() if qid not in incoming]
    if missing:
        raise ValueError("Faltan respuestas obligatorias.")

    q_rows: Dict[UUID, HealthQuestionBank] = {
        q.id: q
        for q in db.query(HealthQuestionBank).filter(HealthQuestionBank.id.in_(list(expected_questions.keys()))).all()
    }

    sub = HealthQuestionnaireSubmission(
        patient_user_id=patient.id,
        attending_doctor_user_id=doctor_id,
        template_id=UUID(expected.template_id) if expected.template_id else None,
        initiation="onboarding_after_password",
        template_version=1,
        completed_at=_utcnow(),
    )
    db.add(sub)
    db.flush()

    for qid, (val, txt) in incoming.items():
        q = q_rows.get(qid)
        if q is None:
            continue
        value, text_repr = _coerce_answer(q, val, txt)
        db.add(
            HealthQuestionnaireAnswer(
                submission_id=sub.id,
                question_id=qid,
                answer_text=text_repr,
                answer_value=value,
            )
        )

    comp = PatientHealthCompletion(
        patient_user_id=patient.id,
        last_submission_id=sub.id,
        completed_at=_utcnow(),
    )
    db.add(comp)
    db.commit()

    notify_user_push_and_db(
        db,
        doctor_id,
        title="Cuestionario de salud completado",
        message=f"{patient.name} completó el cuestionario de salud.",
        notification_type="health_questionnaire_completed",
        payload={
            "patient_id": str(patient.id),
            "patient_name": patient.name,
            "submission_id": str(sub.id),
        },
        push_data={
            "type": "health_questionnaire_completed",
            "patient_id": str(patient.id),
            "patient_name": patient.name,
        },
    )
    logger.info("Cuestionario completado patient=%s doctor=%s", patient.id, doctor_id)


# ---------------------------------------------------------------------------
# Gestión del doctor (catálogo nuevo)
# ---------------------------------------------------------------------------


def list_specialties_for_doctor(db: Session, doctor_id: UUID) -> SpecialtiesListResponse:
    seed_catalog_if_empty(db)
    specs = db.query(HealthSpecialty).order_by(HealthSpecialty.sort_order.asc()).all()

    q_rows = (
        db.query(HealthQuestionBank)
        .filter(
            (HealthQuestionBank.owner_doctor_user_id == doctor_id)
            | (HealthQuestionBank.owner_doctor_user_id.is_(None))
        )
        .all()
    )
    # conteos por (specialty_code or "__global__", active?)
    counts: Dict[str, Dict[str, int]] = defaultdict(lambda: {"total": 0, "active": 0, "inactive": 0})
    for q in q_rows:
        key = q.specialty_code or "__global__"
        counts[key]["total"] += 1
        if _question_is_active_for_doctor(db, doctor_id, q):
            counts[key]["active"] += 1
        else:
            counts[key]["inactive"] += 1

    out_specs = [
        SpecialtyOut(
            code=s.code,
            label=s.label,
            description=s.description,
            icon_key=s.icon_key,
            sort_order=s.sort_order,
            total=counts[s.code]["total"],
            active=counts[s.code]["active"],
            inactive=counts[s.code]["inactive"],
        )
        for s in specs
    ]
    g = counts["__global__"]
    return SpecialtiesListResponse(
        specialties=out_specs,
        global_total=g["total"],
        global_active=g["active"],
        global_inactive=g["inactive"],
    )


def _to_doctor_out(db: Session, q: HealthQuestionBank, doctor_id: UUID) -> DoctorQuestionOut:
    is_active = _question_is_active_for_doctor(db, doctor_id, q)
    return DoctorQuestionOut(
        id=str(q.id),
        prompt=q.prompt,
        specialty_code=q.specialty_code,
        specialty_label=q.specialty_label,
        question_type=q.question_type or "short_text",  # type: ignore[arg-type]
        options=list(q.options) if q.options else None,
        is_required=bool(q.is_required),
        show_in_history=bool(q.show_in_history),
        help_text=q.help_text,
        is_active=is_active,
        is_owned_by_doctor=q.owner_doctor_user_id == doctor_id,
        sort_order=q.sort_order,
    )


def list_questions_for_doctor(
    db: Session,
    doctor_id: UUID,
    *,
    specialty_code: Optional[str],  # None => globales
    status: str = "all",  # all | active | inactive
    search: Optional[str] = None,
) -> DoctorQuestionListResponse:
    seed_catalog_if_empty(db)
    q = db.query(HealthQuestionBank).filter(
        (HealthQuestionBank.owner_doctor_user_id == doctor_id)
        | (HealthQuestionBank.owner_doctor_user_id.is_(None))
    )
    if specialty_code is None:
        q = q.filter(HealthQuestionBank.specialty_code.is_(None))
    else:
        q = q.filter(HealthQuestionBank.specialty_code == specialty_code)
    if search:
        like = f"%{search.strip()}%"
        q = q.filter(HealthQuestionBank.prompt.ilike(like))
    q_rows = q.order_by(HealthQuestionBank.sort_order.asc(), HealthQuestionBank.created_at.asc()).all()

    items = [_to_doctor_out(db, row, doctor_id) for row in q_rows]
    if status == "active":
        items = [x for x in items if x.is_active]
    elif status == "inactive":
        items = [x for x in items if not x.is_active]

    total = len(q_rows)
    active = sum(1 for x in [_to_doctor_out(db, r, doctor_id) for r in q_rows] if x.is_active)
    inactive = total - active
    return DoctorQuestionListResponse(items=items, total=total, active=active, inactive=inactive)


def create_doctor_question(db: Session, doctor: User, body: DoctorQuestionCreateRequest) -> DoctorQuestionOut:
    seed_catalog_if_empty(db)
    if body.question_type not in VALID_QUESTION_TYPES:
        raise ValueError("Tipo de pregunta no válido")
    if body.question_type in ("single_choice", "multi_choice") and not (body.options and len(body.options) >= 2):
        raise ValueError("Las preguntas de opciones requieren al menos 2 opciones")
    if body.specialty_code is not None:
        sp = db.query(HealthSpecialty).filter(HealthSpecialty.code == body.specialty_code).first()
        if sp is None:
            raise ValueError("Especialidad desconocida")
        spec_label = sp.label
    else:
        spec_label = None

    max_order = (
        db.query(HealthQuestionBank)
        .filter(
            HealthQuestionBank.owner_doctor_user_id == doctor.id,
            HealthQuestionBank.specialty_code == body.specialty_code,
        )
        .count()
    )
    q = HealthQuestionBank(
        section=("specialty" if body.specialty_code else "general"),
        specialty_code=body.specialty_code,
        specialty_label=spec_label,
        prompt=body.prompt.strip(),
        sort_order=1000 + max_order,
        is_active=True,
        source="doctor_custom",
        created_by_user_id=doctor.id,
        owner_doctor_user_id=doctor.id,
        question_type=body.question_type,
        options=body.options,
        is_required=body.is_required,
        show_in_history=body.show_in_history,
        help_text=(body.help_text or None),
    )
    db.add(q)
    db.commit()
    db.refresh(q)
    return _to_doctor_out(db, q, doctor.id)


def update_doctor_question(
    db: Session, doctor: User, question_id: UUID, body: DoctorQuestionUpdateRequest
) -> DoctorQuestionOut:
    seed_catalog_if_empty(db)
    q = db.query(HealthQuestionBank).filter(HealthQuestionBank.id == question_id).first()
    if q is None:
        raise ValueError("Pregunta no encontrada")

    if q.owner_doctor_user_id is not None and q.owner_doctor_user_id != doctor.id:
        raise PermissionError("No puedes editar preguntas de otro doctor")

    # Para preguntas de Keepi, solo permitimos togglear visibilidad (is_active)
    if q.owner_doctor_user_id is None:
        if body.is_active is None or any(
            x is not None for x in [
                body.prompt, body.specialty_code, body.question_type, body.options,
                body.is_required, body.show_in_history, body.help_text, body.sort_order,
            ]
        ):
            if body.is_active is None:
                raise ValueError("Solo se puede activar/desactivar preguntas de Keepi")
            # Ignoramos silenciosamente los demás campos
        _set_seed_question_visibility(db, doctor.id, q, bool(body.is_active))
        db.commit()
        db.refresh(q)
        return _to_doctor_out(db, q, doctor.id)

    # Preguntas propias del doctor: CRUD completo
    if body.prompt is not None:
        q.prompt = body.prompt.strip()
    if body.specialty_code is not None:
        if body.specialty_code == "":
            q.specialty_code = None
            q.specialty_label = None
            q.section = "general"
        else:
            sp = db.query(HealthSpecialty).filter(HealthSpecialty.code == body.specialty_code).first()
            if sp is None:
                raise ValueError("Especialidad desconocida")
            q.specialty_code = sp.code
            q.specialty_label = sp.label
            q.section = "specialty"
    if body.question_type is not None:
        if body.question_type not in VALID_QUESTION_TYPES:
            raise ValueError("Tipo de pregunta no válido")
        q.question_type = body.question_type
    if body.options is not None:
        q.options = body.options or None
    if body.is_required is not None:
        q.is_required = bool(body.is_required)
    if body.show_in_history is not None:
        q.show_in_history = bool(body.show_in_history)
    if body.help_text is not None:
        q.help_text = body.help_text or None
    if body.is_active is not None:
        q.is_active = bool(body.is_active)
    if body.sort_order is not None:
        q.sort_order = int(body.sort_order)

    if q.question_type in ("single_choice", "multi_choice") and not (q.options and len(q.options) >= 2):
        raise ValueError("Las preguntas de opciones requieren al menos 2 opciones")

    db.commit()
    db.refresh(q)
    return _to_doctor_out(db, q, doctor.id)


def delete_doctor_question(db: Session, doctor: User, question_id: UUID) -> None:
    q = db.query(HealthQuestionBank).filter(HealthQuestionBank.id == question_id).first()
    if q is None:
        raise ValueError("Pregunta no encontrada")
    if q.owner_doctor_user_id is None:
        raise PermissionError("No puedes borrar preguntas de Keepi; solo desactivarlas")
    if q.owner_doctor_user_id != doctor.id:
        raise PermissionError("No puedes borrar preguntas de otro doctor")
    db.delete(q)
    db.commit()


def toggle_question_active_for_doctor(
    db: Session, doctor: User, question_id: UUID, is_active: bool
) -> DoctorQuestionOut:
    q = db.query(HealthQuestionBank).filter(HealthQuestionBank.id == question_id).first()
    if q is None:
        raise ValueError("Pregunta no encontrada")

    if q.owner_doctor_user_id is None:
        _set_seed_question_visibility(db, doctor.id, q, is_active)
    elif q.owner_doctor_user_id == doctor.id:
        q.is_active = bool(is_active)
    else:
        raise PermissionError("No puedes modificar preguntas de otro doctor")

    db.commit()
    db.refresh(q)
    return _to_doctor_out(db, q, doctor.id)


def _set_seed_question_visibility(
    db: Session, doctor_id: UUID, q: HealthQuestionBank, is_visible: bool
) -> None:
    ov = (
        db.query(HealthQuestionDoctorVisibility)
        .filter(
            HealthQuestionDoctorVisibility.doctor_user_id == doctor_id,
            HealthQuestionDoctorVisibility.question_id == q.id,
        )
        .first()
    )
    if ov is None:
        db.add(
            HealthQuestionDoctorVisibility(
                doctor_user_id=doctor_id,
                question_id=q.id,
                is_visible=is_visible,
            )
        )
    else:
        ov.is_visible = is_visible


def reorder_doctor_questions(
    db: Session, doctor: User, body: DoctorQuestionReorderRequest
) -> None:
    for item in body.items:
        try:
            qid = UUID(item.question_id)
        except Exception:
            continue
        q = db.query(HealthQuestionBank).filter(HealthQuestionBank.id == qid).first()
        if q is None or q.owner_doctor_user_id != doctor.id:
            continue
        q.sort_order = int(item.sort_order)
    db.commit()


# ---------------------------------------------------------------------------
# Plantillas personalizadas
# ---------------------------------------------------------------------------


def _template_out(tpl: HealthQuestionnaireTemplate) -> TemplateOut:
    return TemplateOut(
        id=str(tpl.id),
        name=tpl.name,
        description=tpl.description,
        questions_count=len(tpl.questions or []),
        assigned_count=len(tpl.assignments or []),
        created_at=tpl.created_at,
    )


def _template_detail(db: Session, tpl: HealthQuestionnaireTemplate) -> TemplateDetailOut:
    qs: List[TemplateQuestionOut] = []
    for tq in sorted(tpl.questions or [], key=lambda x: x.sort_order):
        q = tq.question
        if q is None:
            continue
        qs.append(
            TemplateQuestionOut(
                question_id=str(q.id),
                prompt=q.prompt,
                question_type=q.question_type or "short_text",  # type: ignore[arg-type]
                specialty_code=q.specialty_code,
                specialty_label=q.specialty_label,
                sort_order=tq.sort_order,
            )
        )
    assignments = [str(a.patient_user_id) for a in (tpl.assignments or [])]
    return TemplateDetailOut(
        id=str(tpl.id),
        name=tpl.name,
        description=tpl.description,
        questions_count=len(qs),
        assigned_count=len(assignments),
        created_at=tpl.created_at,
        questions=qs,
        assigned_patient_ids=assignments,
    )


def list_templates(db: Session, doctor: User) -> TemplateListResponse:
    seed_catalog_if_empty(db)
    rows = (
        db.query(HealthQuestionnaireTemplate)
        .filter(HealthQuestionnaireTemplate.doctor_user_id == doctor.id)
        .order_by(HealthQuestionnaireTemplate.created_at.desc())
        .all()
    )
    return TemplateListResponse(templates=[_template_out(r) for r in rows])


def get_template_detail(db: Session, doctor: User, template_id: UUID) -> TemplateDetailOut:
    tpl = (
        db.query(HealthQuestionnaireTemplate)
        .filter(
            HealthQuestionnaireTemplate.id == template_id,
            HealthQuestionnaireTemplate.doctor_user_id == doctor.id,
        )
        .first()
    )
    if tpl is None:
        raise ValueError("Plantilla no encontrada")
    return _template_detail(db, tpl)


def _validate_question_ids_for_doctor(db: Session, doctor_id: UUID, q_ids: Iterable[str]) -> List[UUID]:
    uuids: List[UUID] = []
    for raw in q_ids:
        try:
            uuids.append(UUID(str(raw)))
        except Exception:
            raise ValueError(f"ID de pregunta inválido: {raw}")
    rows = db.query(HealthQuestionBank).filter(HealthQuestionBank.id.in_(uuids)).all()
    by_id = {r.id: r for r in rows}
    for uid in uuids:
        r = by_id.get(uid)
        if r is None:
            raise ValueError(f"Pregunta no encontrada: {uid}")
        if r.owner_doctor_user_id is not None and r.owner_doctor_user_id != doctor_id:
            raise PermissionError("No puedes usar preguntas de otro doctor")
    return uuids


def create_template(db: Session, doctor: User, body: TemplateCreateRequest) -> TemplateDetailOut:
    seed_catalog_if_empty(db)
    q_uuids = _validate_question_ids_for_doctor(db, doctor.id, body.question_ids)
    tpl = HealthQuestionnaireTemplate(
        doctor_user_id=doctor.id,
        name=body.name.strip(),
        description=(body.description or None),
    )
    db.add(tpl)
    db.flush()
    for idx, qid in enumerate(q_uuids):
        db.add(
            HealthQuestionnaireTemplateQuestion(
                template_id=tpl.id,
                question_id=qid,
                sort_order=idx,
            )
        )
    db.commit()
    db.refresh(tpl)
    return _template_detail(db, tpl)


def update_template(
    db: Session, doctor: User, template_id: UUID, body: TemplateUpdateRequest
) -> TemplateDetailOut:
    tpl = (
        db.query(HealthQuestionnaireTemplate)
        .filter(
            HealthQuestionnaireTemplate.id == template_id,
            HealthQuestionnaireTemplate.doctor_user_id == doctor.id,
        )
        .first()
    )
    if tpl is None:
        raise ValueError("Plantilla no encontrada")
    if body.name is not None:
        tpl.name = body.name.strip()
    if body.description is not None:
        tpl.description = body.description or None
    if body.question_ids is not None:
        q_uuids = _validate_question_ids_for_doctor(db, doctor.id, body.question_ids)
        db.query(HealthQuestionnaireTemplateQuestion).filter(
            HealthQuestionnaireTemplateQuestion.template_id == tpl.id
        ).delete(synchronize_session=False)
        for idx, qid in enumerate(q_uuids):
            db.add(
                HealthQuestionnaireTemplateQuestion(
                    template_id=tpl.id,
                    question_id=qid,
                    sort_order=idx,
                )
            )
    db.commit()
    db.refresh(tpl)
    return _template_detail(db, tpl)


def delete_template(db: Session, doctor: User, template_id: UUID) -> None:
    tpl = (
        db.query(HealthQuestionnaireTemplate)
        .filter(
            HealthQuestionnaireTemplate.id == template_id,
            HealthQuestionnaireTemplate.doctor_user_id == doctor.id,
        )
        .first()
    )
    if tpl is None:
        raise ValueError("Plantilla no encontrada")
    db.delete(tpl)
    db.commit()


def assign_template_to_patients(
    db: Session, doctor: User, template_id: UUID, body: TemplateAssignRequest
) -> TemplateDetailOut:
    tpl = (
        db.query(HealthQuestionnaireTemplate)
        .filter(
            HealthQuestionnaireTemplate.id == template_id,
            HealthQuestionnaireTemplate.doctor_user_id == doctor.id,
        )
        .first()
    )
    if tpl is None:
        raise ValueError("Plantilla no encontrada")

    for raw in body.patient_user_ids:
        try:
            pid = UUID(str(raw))
        except Exception:
            raise ValueError(f"ID de paciente inválido: {raw}")
        patient = db.query(User).filter(User.id == pid).first()
        if patient is None or patient.created_by_user_id != doctor.id:
            raise PermissionError("No puedes asignar a un paciente que no es tuyo")
        # Remover asignaciones previas de ese paciente a otras plantillas del doctor
        db.query(HealthQuestionnaireTemplateAssignment).filter(
            HealthQuestionnaireTemplateAssignment.patient_user_id == pid,
            HealthQuestionnaireTemplateAssignment.template_id.in_(
                db.query(HealthQuestionnaireTemplate.id).filter(
                    HealthQuestionnaireTemplate.doctor_user_id == doctor.id
                )
            ),
        ).delete(synchronize_session=False)
        db.add(HealthQuestionnaireTemplateAssignment(template_id=tpl.id, patient_user_id=pid))
    db.commit()
    db.refresh(tpl)
    return _template_detail(db, tpl)


def unassign_template_from_patient(
    db: Session, doctor: User, template_id: UUID, patient_id: UUID
) -> None:
    tpl = (
        db.query(HealthQuestionnaireTemplate)
        .filter(
            HealthQuestionnaireTemplate.id == template_id,
            HealthQuestionnaireTemplate.doctor_user_id == doctor.id,
        )
        .first()
    )
    if tpl is None:
        raise ValueError("Plantilla no encontrada")
    db.query(HealthQuestionnaireTemplateAssignment).filter(
        HealthQuestionnaireTemplateAssignment.template_id == tpl.id,
        HealthQuestionnaireTemplateAssignment.patient_user_id == patient_id,
    ).delete(synchronize_session=False)
    db.commit()


# ---------------------------------------------------------------------------
# Legacy (pantalla antigua de ajustes)
# ---------------------------------------------------------------------------


def get_doctor_settings(db: Session, doctor: User) -> DoctorQuestionnaireSettingsResponse:
    seed_catalog_if_empty(db)
    doctor_id = doctor.id
    custom = _doctor_has_any_visibility_row(db, doctor_id)
    q_rows = (
        db.query(HealthQuestionBank)
        .filter(HealthQuestionBank.is_active.is_(True), HealthQuestionBank.owner_doctor_user_id.is_(None))
        .order_by(HealthQuestionBank.sort_order.asc())
        .all()
    )
    items: List[DoctorQuestionSettingRow] = []
    for q in q_rows:
        visible = _seed_question_visible_for_doctor(db, doctor_id, q)
        ov = (
            db.query(HealthQuestionDoctorVisibility)
            .filter(
                HealthQuestionDoctorVisibility.doctor_user_id == doctor_id,
                HealthQuestionDoctorVisibility.question_id == q.id,
            )
            .first()
        )
        items.append(
            DoctorQuestionSettingRow(
                question_id=str(q.id),
                section=q.section,
                specialty_code=q.specialty_code,
                specialty_label=q.specialty_label,
                prompt=q.prompt,
                sort_order=q.sort_order,
                is_visible=visible,
                has_doctor_override=ov is not None,
            )
        )
    return DoctorQuestionnaireSettingsResponse(items=items, doctor_has_customization=custom)


def patch_doctor_settings(
    db: Session, doctor: User, body: DoctorQuestionnaireSettingsPatchRequest
) -> DoctorQuestionnaireSettingsResponse:
    seed_catalog_if_empty(db)
    valid_ids = {
        str(r.id)
        for r in db.query(HealthQuestionBank)
        .filter(HealthQuestionBank.is_active.is_(True), HealthQuestionBank.owner_doctor_user_id.is_(None))
        .all()
    }
    for item in body.visibilities:
        if item.question_id not in valid_ids:
            raise ValueError(f"Pregunta no válida: {item.question_id}")
        q_uuid = UUID(item.question_id)
        q = db.query(HealthQuestionBank).filter(HealthQuestionBank.id == q_uuid).first()
        if q is None:
            continue
        _set_seed_question_visibility(db, doctor.id, q, bool(item.is_visible))
    db.commit()
    return get_doctor_settings(db, doctor)
