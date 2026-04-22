"""Publicar cuestionario personalizado por doctor desde payload JSON."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.questionnaire_catalog import (
    DoctorQuestionnaireSettings,
    QuestionnaireQuestion,
    QuestionnaireQuestionOption,
    QuestionnaireTemplate,
    QuestionnaireVersion,
)
from app.models.user import User

ALLOWED_RESPONSE_TYPES = frozenset(
    {
        "single_choice",
        "multiple_choice_grid",
        "likert_emoji",
        "number",
        "height_picker",
        "scale_numeric",
        "short_text",
        "long_text",
    }
)


def publish_custom_from_payload(
    db: Session,
    doctor: User,
    *,
    include_base: bool,
    questions: list[dict],
) -> QuestionnaireVersion:
    """
    include_base: si True, el cliente debe haber enviado también preguntas base en `questions`
    (el front compone la lista desde el pool permitido). Si False, solo especialidad u orden propio.
    """
    if doctor.specialty_id is None:
        raise ValueError("El doctor debe tener especialidad asignada.")
    if not questions:
        raise ValueError("Debe haber al menos una pregunta.")

    slug = f"doctor_custom_{doctor.id}"
    tmpl = db.query(QuestionnaireTemplate).filter(QuestionnaireTemplate.slug == slug).first()
    if not tmpl:
        tmpl = QuestionnaireTemplate(
            slug=slug,
            scope="doctor_custom",
            title="Cuestionario personalizado",
            owner_user_id=doctor.id,
            medical_specialty_id=doctor.specialty_id,
        )
        db.add(tmpl)
        db.flush()
    else:
        tmpl.medical_specialty_id = doctor.specialty_id

    max_v = (
        db.query(QuestionnaireVersion)
        .filter(QuestionnaireVersion.template_id == tmpl.id)
        .order_by(QuestionnaireVersion.version.desc())
        .first()
    )
    next_n = (max_v.version + 1) if max_v else 1

    ver = QuestionnaireVersion(
        template_id=tmpl.id,
        version=next_n,
        is_published=True,
        published_at=datetime.now(timezone.utc),
    )
    db.add(ver)
    db.flush()

    for i, raw in enumerate(questions):
        rt = raw.get("response_type")
        if rt not in ALLOWED_RESPONSE_TYPES:
            raise ValueError(f"response_type no permitido: {rt}")
        q = QuestionnaireQuestion(
            version_id=ver.id,
            order_index=raw.get("order_index", i),
            section_key=raw.get("section_key"),
            prompt=raw["prompt"],
            help_text=raw.get("help_text"),
            response_type=rt,
            config=raw.get("config") or {},
        )
        db.add(q)
        db.flush()
        for opt in raw.get("options") or []:
            db.add(
                QuestionnaireQuestionOption(
                    question_id=q.id,
                    value=opt["value"],
                    label=opt["label"],
                    icon_key=opt.get("icon_key"),
                    order_index=opt.get("order_index", 0),
                )
            )

    st = db.query(DoctorQuestionnaireSettings).filter(DoctorQuestionnaireSettings.doctor_id == doctor.id).first()
    if not st:
        st = DoctorQuestionnaireSettings(
            doctor_id=doctor.id,
            medical_specialty_id=doctor.specialty_id,
            mode="custom",
            include_base_in_custom=include_base,
            active_version_id=ver.id,
        )
        db.add(st)
    else:
        st.mode = "custom"
        st.include_base_in_custom = include_base
        st.active_version_id = ver.id
        st.medical_specialty_id = doctor.specialty_id

    db.commit()
    db.refresh(ver)
    return ver
