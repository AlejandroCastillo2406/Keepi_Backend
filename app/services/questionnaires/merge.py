"""Materializa versión activa (base + especialidad) para un doctor."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.medical_specialty import MedicalSpecialty
from app.models.questionnaire_catalog import (
    DoctorQuestionnaireSettings,
    QuestionnaireQuestion,
    QuestionnaireQuestionOption,
    QuestionnaireTemplate,
    QuestionnaireVersion,
)
from app.models.user import User


def latest_published_for_slug(db: Session, slug: str) -> QuestionnaireVersion | None:
    t = db.query(QuestionnaireTemplate).filter(QuestionnaireTemplate.slug == slug).first()
    if not t:
        return None
    return (
        db.query(QuestionnaireVersion)
        .filter(QuestionnaireVersion.template_id == t.id, QuestionnaireVersion.is_published.is_(True))
        .order_by(QuestionnaireVersion.version.desc())
        .first()
    )


def specialty_slug_for_code(code: str) -> str:
    return f"specialty_{code}"


def materialize_system_composed(db: Session, doctor: User) -> QuestionnaireVersion:
    if doctor.specialty_id is None:
        raise ValueError("El doctor debe tener una especialidad asignada.")

    spec_row = db.query(MedicalSpecialty).filter(MedicalSpecialty.id == doctor.specialty_id).first()
    if not spec_row:
        raise ValueError("Especialidad no encontrada.")

    base_v = latest_published_for_slug(db, "keepi_base")
    if not base_v:
        raise ValueError("Plantilla base Keepi no publicada. Ejecuta el script de seed.")

    spec_slug = specialty_slug_for_code(spec_row.code)
    spec_v = latest_published_for_slug(db, spec_slug)
    if not spec_v:
        raise ValueError(f"No hay plantilla publicada para la especialidad '{spec_row.code}'.")

    slug = f"doctor_merged_{doctor.id}"
    tmpl = db.query(QuestionnaireTemplate).filter(QuestionnaireTemplate.slug == slug).first()
    if not tmpl:
        tmpl = QuestionnaireTemplate(
            slug=slug,
            scope="doctor_merged",
            title="Cuestionario combinado",
            owner_user_id=doctor.id,
            medical_specialty_id=doctor.specialty_id,
        )
        db.add(tmpl)
        db.flush()

    max_v = (
        db.query(QuestionnaireVersion)
        .filter(QuestionnaireVersion.template_id == tmpl.id)
        .order_by(QuestionnaireVersion.version.desc())
        .first()
    )
    next_n = (max_v.version + 1) if max_v else 1

    new_ver = QuestionnaireVersion(
        template_id=tmpl.id,
        version=next_n,
        is_published=True,
        published_at=datetime.now(timezone.utc),
    )
    db.add(new_ver)
    db.flush()

    order = 0
    for source_v in (base_v, spec_v):
        qs = (
            db.query(QuestionnaireQuestion)
            .filter(QuestionnaireQuestion.version_id == source_v.id)
            .order_by(QuestionnaireQuestion.order_index)
            .all()
        )
        for q in qs:
            nq = QuestionnaireQuestion(
                version_id=new_ver.id,
                order_index=order,
                section_key=q.section_key,
                prompt=q.prompt,
                help_text=q.help_text,
                response_type=q.response_type,
                config=dict(q.config or {}),
            )
            db.add(nq)
            db.flush()
            order += 1
            for o in sorted(q.options, key=lambda x: x.order_index):
                db.add(
                    QuestionnaireQuestionOption(
                        question_id=nq.id,
                        value=o.value,
                        label=o.label,
                        icon_key=o.icon_key,
                        order_index=o.order_index,
                    )
                )

    st = db.query(DoctorQuestionnaireSettings).filter(DoctorQuestionnaireSettings.doctor_id == doctor.id).first()
    if not st:
        st = DoctorQuestionnaireSettings(
            doctor_id=doctor.id,
            medical_specialty_id=doctor.specialty_id,
            mode="system_composed",
            include_base_in_custom=True,
            active_version_id=new_ver.id,
        )
        db.add(st)
    else:
        st.mode = "system_composed"
        st.active_version_id = new_ver.id
        st.medical_specialty_id = doctor.specialty_id

    db.commit()
    db.refresh(new_ver)
    return new_ver


def ensure_doctor_active_version(db: Session, doctor: User) -> UUID:
    """Devuelve version_id activa; materializa system_composed si hace falta."""
    if doctor.specialty_id is None:
        raise ValueError("Asigna una especialidad al perfil del doctor.")

    st = db.query(DoctorQuestionnaireSettings).filter(DoctorQuestionnaireSettings.doctor_id == doctor.id).first()
    if st and st.active_version_id:
        ver = db.query(QuestionnaireVersion).filter(QuestionnaireVersion.id == st.active_version_id).first()
        if ver and ver.is_published:
            return st.active_version_id

    v = materialize_system_composed(db, doctor)
    return v.id
