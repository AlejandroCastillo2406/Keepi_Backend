"""Serializa versión publicada a esquema API."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.questionnaire_catalog import (
    QuestionnaireQuestion,
    QuestionnaireTemplate,
    QuestionnaireVersion,
    QuestionOptionSchema,
    QuestionSchema,
)


def version_to_questions(db: Session, version_id) -> list[QuestionSchema]:
    qs = (
        db.query(QuestionnaireQuestion)
        .filter(QuestionnaireQuestion.version_id == version_id)
        .order_by(QuestionnaireQuestion.order_index)
        .all()
    )
    out: list[QuestionSchema] = []
    for q in qs:
        opts = sorted(q.options, key=lambda o: o.order_index)
        out.append(
            QuestionSchema(
                id=str(q.id),
                order_index=q.order_index,
                section_key=q.section_key,
                prompt=q.prompt,
                help_text=q.help_text,
                response_type=q.response_type,
                config=dict(q.config or {}),
                options=[
                    QuestionOptionSchema(
                        id=str(o.id),
                        value=o.value,
                        label=o.label,
                        icon_key=o.icon_key,
                        order_index=o.order_index,
                    )
                    for o in opts
                ],
            )
        )
    return out


def version_title(db: Session, version_id) -> str:
    v = (
        db.query(QuestionnaireVersion)
        .filter(QuestionnaireVersion.id == version_id)
        .first()
    )
    if not v:
        return "Diagnóstico"
    tmpl = db.query(QuestionnaireTemplate).filter(QuestionnaireTemplate.id == v.template_id).first()
    if not tmpl:
        return "Diagnóstico"
    return tmpl.title or "Diagnóstico"
