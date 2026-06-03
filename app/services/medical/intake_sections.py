"""Secciones de ficha clínica previa al cuestionario (alta inteligente)."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional

# Orden fijo del wizard en PaginaWebPaciente
INTAKE_SECTION_IDS = [
    "personal_data",
    "consultation_reason",
    "allergies",
    "medications",
    "family_history",
    "surgeries",
    "current_illness",
]

_SECTION_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "personal_data": {
        "title": "Datos personales",
        "subtitle": "Confirma o completa tu información de contacto.",
        "fields": [
            {
                "key": "phone",
                "label": "Teléfono",
                "type": "short_text",
                "required": True,
            },
            {
                "key": "birth_date",
                "label": "Fecha de nacimiento (AAAA-MM-DD)",
                "type": "short_text",
                "required": False,
            },
            {
                "key": "sex",
                "label": "Sexo",
                "type": "single_choice",
                "options": [
                    "Femenino",
                    "Masculino",
                    "Otro",
                    "Prefiero no decir",
                ],
                "required": False,
            },
        ],
    },
    "consultation_reason": {
        "title": "Motivo de consulta",
        "subtitle": "Cuéntanos por qué acudes a consulta.",
        "fields": [
            {
                "key": "reason",
                "label": "Motivo de consulta",
                "type": "long_text",
                "required": True,
            },
        ],
    },
    "allergies": {
        "title": "Alergias",
        "subtitle": "Medicamentos, alimentos u otras sustancias.",
        "fields": [
            {
                "key": "allergies",
                "label": "¿Tienes alergias conocidas?",
                "type": "long_text",
                "required": False,
                "placeholder": "Escribe «Ninguna» si no aplica.",
            },
        ],
    },
    "medications": {
        "title": "Medicamentos actuales",
        "subtitle": "Incluye dosis si la recuerdas.",
        "fields": [
            {
                "key": "medications",
                "label": "Medicamentos que tomas actualmente",
                "type": "long_text",
                "required": False,
                "placeholder": "Escribe «Ninguno» si no aplica.",
            },
        ],
    },
    "family_history": {
        "title": "Antecedentes familiares",
        "subtitle": "Enfermedades relevantes en padres, hermanos o abuelos.",
        "fields": [
            {
                "key": "family_history",
                "label": "Antecedentes familiares",
                "type": "long_text",
                "required": False,
            },
        ],
    },
    "surgeries": {
        "title": "Cirugías previas",
        "subtitle": "Operaciones o procedimientos quirúrgicos.",
        "fields": [
            {
                "key": "surgeries",
                "label": "Cirugías o hospitalizaciones previas",
                "type": "long_text",
                "required": False,
                "placeholder": "Escribe «Ninguna» si no aplica.",
            },
        ],
    },
    "current_illness": {
        "title": "Padecimiento actual",
        "subtitle": "Síntomas y cómo te has sentido recientemente.",
        "fields": [
            {
                "key": "current_illness",
                "label": "Describe tu padecimiento actual",
                "type": "long_text",
                "required": True,
            },
        ],
    },
}

_CONTEXT_PREFILL_MAP = {
    "phone": "phone",
    "birth_date": "birth_date",
    "sex": "sex",
    "reason": "consultation_reason",
}


def build_intake_sections_for_invitation(
    intake_context: Optional[Dict[str, Any]],
    saved_responses: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    ctx = intake_context or {}
    saved = saved_responses or {}
    sections: List[Dict[str, Any]] = []
    for sid in INTAKE_SECTION_IDS:
        tpl = deepcopy(_SECTION_TEMPLATES[sid])
        section_saved = saved.get(sid) if isinstance(saved.get(sid), dict) else {}
        fields_out = []
        for field in tpl["fields"]:
            key = field["key"]
            prefill_key = _CONTEXT_PREFILL_MAP.get(key)
            value = section_saved.get(key)
            if value is None and prefill_key:
                value = ctx.get(prefill_key)
            if value is not None and value != "":
                field = {**field, "value": value}
            fields_out.append(field)
        sections.append(
            {
                "id": sid,
                "title": tpl["title"],
                "subtitle": tpl.get("subtitle"),
                "fields": fields_out,
            }
        )
    return sections


def intake_is_complete(
    sections: List[Dict[str, Any]],
    saved_responses: Dict[str, Any],
) -> bool:
    for section in sections:
        sid = section["id"]
        section_answers = saved_responses.get(sid)
        if not isinstance(section_answers, dict):
            section_answers = {}
        for field in section["fields"]:
            if not field.get("required"):
                continue
            key = field["key"]
            val = section_answers.get(key)
            if val is None or (isinstance(val, str) and not val.strip()):
                return False
    return True


def merge_intake_section(
    saved: Optional[Dict[str, Any]],
    section_id: str,
    answers: Dict[str, Any],
) -> Dict[str, Any]:
    out = dict(saved or {})
    if section_id not in INTAKE_SECTION_IDS:
        return out
    current = out.get(section_id)
    if not isinstance(current, dict):
        current = {}
    merged = {**current, **answers}
    out[section_id] = merged
    return out
