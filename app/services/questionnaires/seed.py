"""Sembrado de especialidades y plantillas desde JSON (sin datos hardcodeados en código)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.medical_specialty import MedicalSpecialty
from app.models.questionnaire_catalog import (
    QuestionnaireQuestion,
    QuestionnaireQuestionOption,
    QuestionnaireTemplate,
    QuestionnaireVersion,
)


def _data_file() -> Path:
    return Path(__file__).resolve().parents[3] / "scripts" / "data" / "questionnaire_seed.json"


def load_json() -> dict[str, Any]:
    with open(_data_file(), encoding="utf-8") as f:
        return json.load(f)


def seed_specialties(db: Session, data: dict[str, Any]) -> dict[str, UUID]:
    out: dict[str, UUID] = {}
    for row in data.get("specialties", []):
        code = row["code"]
        ex = db.query(MedicalSpecialty).filter(MedicalSpecialty.code == code).first()
        if ex:
            out[code] = ex.id
            continue
        m = MedicalSpecialty(code=code, name_es=row["name_es"])
        db.add(m)
        db.flush()
        out[code] = m.id
    return out


def seed_all_if_needed(db: Session) -> bool:
    """Inserta plantillas publicadas si faltan. Retorna True si hubo inserciones."""
    data = load_json()
    spec_map = seed_specialties(db, data)
    db.commit()

    did = False
    for tmpl in data.get("templates", []):
        slug = tmpl["slug"]
        t = db.query(QuestionnaireTemplate).filter(QuestionnaireTemplate.slug == slug).first()
        if t:
            pub = (
                db.query(QuestionnaireVersion)
                .filter(
                    QuestionnaireVersion.template_id == t.id,
                    QuestionnaireVersion.is_published.is_(True),
                )
                .first()
            )
            if pub:
                continue

        did = True
        spec_code = tmpl.get("specialty_code")
        spec_id = spec_map.get(spec_code) if spec_code else None

        if not t:
            t = QuestionnaireTemplate(
                slug=slug,
                scope=tmpl["scope"],
                title=tmpl.get("title", slug),
                owner_user_id=None,
                medical_specialty_id=spec_id,
            )
            db.add(t)
            db.flush()
        else:
            t.medical_specialty_id = spec_id
            t.title = tmpl.get("title", slug)

        v = QuestionnaireVersion(
            template_id=t.id,
            version=1,
            is_published=True,
            published_at=datetime.now(timezone.utc),
        )
        db.add(v)
        db.flush()

        for i, step in enumerate(tmpl.get("steps", [])):
            q = QuestionnaireQuestion(
                version_id=v.id,
                order_index=i,
                section_key=step.get("section_key"),
                prompt=step["prompt"],
                help_text=step.get("help_text") or None,
                response_type=step["response_type"],
                config=step.get("config") or {},
            )
            db.add(q)
            db.flush()
            for opt in step.get("options") or []:
                db.add(
                    QuestionnaireQuestionOption(
                        question_id=q.id,
                        value=opt["value"],
                        label=opt["label"],
                        icon_key=opt.get("icon_key"),
                        order_index=opt.get("order_index", 0),
                    )
                )

    if did:
        db.commit()
    return did
