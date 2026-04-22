"""Lógica del cuestionario de salud: banco de preguntas, visibilidad por médico y envíos."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.roles import ROLE_PATIENT
from app.models.health_questionnaire import (
    DoctorQuestionnaireSettingsPatchRequest,
    DoctorQuestionnaireSettingsResponse,
    DoctorQuestionSettingRow,
    HealthQuestionBank,
    HealthQuestionDoctorVisibility,
    HealthQuestionnaireAnswer,
    HealthQuestionnaireSubmission,
    PatientHealthCompletion,
    QuestionnaireForPatientResponse,
    QuestionnaireQuestionOut,
    QuestionnaireSectionOut,
    QuestionnaireSubmitRequest,
)
from app.models.user import User, UserResponse
from app.services.notificaciones.user_notify import notify_user_push_and_db

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def build_user_response_with_flags(db: Session, user: User) -> UserResponse:
    """UserResponse con bandera de cuestionario pendiente (paciente dado de alta por médico)."""
    seed_catalog_if_empty(db)
    pending = patient_must_complete_questionnaire(db, user)
    return UserResponse.from_orm(user, pending_health_questionnaire=pending)


def patient_must_complete_questionnaire(db: Session, user: User) -> bool:
    """Paciente creado por médico y aún sin primera respuesta del cuestionario."""
    if user.role is None or user.role.name != ROLE_PATIENT:
        return False
    if user.created_by_user_id is None:
        return False
    row = db.query(PatientHealthCompletion).filter(PatientHealthCompletion.patient_user_id == user.id).first()
    return row is None


def _doctor_has_any_visibility_row(db: Session, doctor_id: UUID) -> bool:
    n = db.query(HealthQuestionDoctorVisibility).filter(HealthQuestionDoctorVisibility.doctor_user_id == doctor_id).count()
    return n > 0


def _question_visible_for_patient(db: Session, doctor_id: UUID, question_id: UUID) -> bool:
    if not _doctor_has_any_visibility_row(db, doctor_id):
        return True
    row = (
        db.query(HealthQuestionDoctorVisibility)
        .filter(
            HealthQuestionDoctorVisibility.doctor_user_id == doctor_id,
            HealthQuestionDoctorVisibility.question_id == question_id,
        )
        .first()
    )
    if row is None:
        return False
    return bool(row.is_visible)


def seed_catalog_if_empty(db: Session) -> None:
    if db.query(HealthQuestionBank).count() > 0:
        return
    rows: List[Tuple[str, Optional[str], Optional[str], str, int]] = [
        ("general", None, None, "¿Cuál es el motivo principal de su consulta o seguimiento en este momento?", 10),
        ("general", None, None, "¿Toma medicamentos de forma regular? Descríbalos brevemente (nombre o principio activo si lo conoce).", 20),
        ("general", None, None, "¿Tiene alergias conocidas a medicamentos, alimentos u otras sustancias?", 30),
        ("general", None, None, "¿Ha tenido cirugías u hospitalizaciones en el último año? Indique cuál y la fecha aproximada si la recuerda.", 40),
        ("general", None, None, "¿Cómo calificaría su nivel de estrés o carga emocional en las últimas semanas? (breve descripción)", 50),
        ("specialty", "cardiologia", "Cardiología", "¿Ha sentido dolor u opresión en el pecho, palpitaciones o mareos frecuentes recientemente?", 100),
        ("specialty", "cardiologia", "Cardiología", "¿Tiene antecedentes familiares de enfermedad cardiovascular (infarto, ACV antes de los 55 años)?", 110),
        ("specialty", "endocrinologia", "Endocrinología", "¿Le han diagnosticado diabetes, resistencia a la insulina o alteraciones de la tiroides?", 200),
        ("specialty", "endocrinologia", "Endocrinología", "¿Ha medido glucosa en ayunas o HbA1c recientemente? Indique valores si los conoce.", 210),
        ("specialty", "ginecologia", "Ginecología", "¿Hay posibilidad de embarazo actual o está en periodo de lactancia?", 300),
        ("specialty", "ginecologia", "Ginecología", "¿Desea mencionar fecha aproximada de última menstruación o cualquier síntoma ginecológico relevante?", 310),
        ("specialty", "medicina_general", "Medicina general", "¿Ha tenido fiebre, pérdida de peso no intencionada o fatiga persistente en las últimas semanas?", 400),
    ]
    for section, spec_code, spec_label, prompt, sort_order in rows:
        db.add(
            HealthQuestionBank(
                section=section,
                specialty_code=spec_code,
                specialty_label=spec_label,
                prompt=prompt,
                sort_order=sort_order,
                is_active=True,
                source="seed",
            )
        )
    db.commit()
    logger.info("Catálogo de cuestionario de salud sembrado (%s preguntas)", len(rows))


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
    q_rows = (
        db.query(HealthQuestionBank)
        .filter(HealthQuestionBank.is_active.is_(True))
        .order_by(HealthQuestionBank.sort_order.asc(), HealthQuestionBank.id.asc())
        .all()
    )
    visible: List[HealthQuestionBank] = []
    for q in q_rows:
        if not _question_visible_for_patient(db, doctor_id, q.id):
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
                questions=[QuestionnaireQuestionOut(id=str(x.id), prompt=x.prompt) for x in sorted(items, key=lambda z: z.sort_order)],
            )
        )

    msg = None
    if not _doctor_has_any_visibility_row(db, doctor_id):
        msg = (
            "Tu médico aún no personalizó el cuestionario en Ajustes. "
            "Por ahora verás preguntas generales y de varias especialidades; cuando lo configure, "
            "solo se mostrarán las que él elija."
        )

    return QuestionnaireForPatientResponse(completed=False, message=msg, sections=sections)


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

    expected_ids = {UUID(q.id) for sec in expected.sections for q in sec.questions}
    by_id: Dict[UUID, str] = {}
    for a in body.answers:
        by_id[UUID(str(a.question_id))] = a.answer_text.strip()
    if set(by_id.keys()) != expected_ids:
        raise ValueError("Debes responder exactamente todas las preguntas mostradas.")

    sub = HealthQuestionnaireSubmission(
        patient_user_id=patient.id,
        attending_doctor_user_id=doctor_id,
        initiation="onboarding_after_password",
        template_version=1,
        completed_at=_utcnow(),
    )
    db.add(sub)
    db.flush()

    for qid, text in by_id.items():
        db.add(
            HealthQuestionnaireAnswer(
                submission_id=sub.id,
                question_id=qid,
                answer_text=text,
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


def get_doctor_settings(db: Session, doctor: User) -> DoctorQuestionnaireSettingsResponse:
    seed_catalog_if_empty(db)
    doctor_id = doctor.id
    custom = _doctor_has_any_visibility_row(db, doctor_id)
    q_rows = (
        db.query(HealthQuestionBank)
        .filter(HealthQuestionBank.is_active.is_(True))
        .order_by(HealthQuestionBank.sort_order.asc())
        .all()
    )
    items: List[DoctorQuestionSettingRow] = []
    for q in q_rows:
        ov = (
            db.query(HealthQuestionDoctorVisibility)
            .filter(
                HealthQuestionDoctorVisibility.doctor_user_id == doctor_id,
                HealthQuestionDoctorVisibility.question_id == q.id,
            )
            .first()
        )
        if custom and ov is None:
            visible = False
            has_ov = False
        elif ov is not None:
            visible = bool(ov.is_visible)
            has_ov = True
        else:
            visible = True
            has_ov = False
        items.append(
            DoctorQuestionSettingRow(
                question_id=str(q.id),
                section=q.section,
                specialty_code=q.specialty_code,
                specialty_label=q.specialty_label,
                prompt=q.prompt,
                sort_order=q.sort_order,
                is_visible=visible,
                has_doctor_override=has_ov,
            )
        )
    return DoctorQuestionnaireSettingsResponse(items=items, doctor_has_customization=custom)


def patch_doctor_settings(db: Session, doctor: User, body: DoctorQuestionnaireSettingsPatchRequest) -> DoctorQuestionnaireSettingsResponse:
    seed_catalog_if_empty(db)
    doctor_id = doctor.id
    valid_ids = {str(r.id) for r in db.query(HealthQuestionBank).filter(HealthQuestionBank.is_active.is_(True)).all()}
    for item in body.visibilities:
        if item.question_id not in valid_ids:
            raise ValueError(f"Pregunta no válida: {item.question_id}")
        q_uuid = UUID(item.question_id)
        row = (
            db.query(HealthQuestionDoctorVisibility)
            .filter(
                HealthQuestionDoctorVisibility.doctor_user_id == doctor_id,
                HealthQuestionDoctorVisibility.question_id == q_uuid,
            )
            .first()
        )
        if row is None:
            db.add(
                HealthQuestionDoctorVisibility(
                    doctor_user_id=doctor_id,
                    question_id=q_uuid,
                    is_visible=item.is_visible,
                )
            )
        else:
            row.is_visible = item.is_visible
    db.commit()
    return get_doctor_settings(db, doctor)
