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
]

_SECTION_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "personal_data": {
        "title": "Datos personales",
        "subtitle": "Confirma o completa tu información de contacto.",
        "fields": [
            {
                "key": "phone",
                "label": "Teléfono",
                "type": "phone",
                "required": True,
                "placeholder": "10 dígitos",
            },
            {
                "key": "birth_date",
                "label": "Fecha de nacimiento",
                "type": "date",
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
            {
                "key": "weight_kg",
                "label": "Peso (kg)",
                "type": "short_text",
                "required": False,
                "placeholder": "Ej. 64",
            },
            {
                "key": "blood_type",
                "label": "Tipo de sangre",
                "type": "single_choice",
                "options": [
                    "O+",
                    "O-",
                    "A+",
                    "A-",
                    "B+",
                    "B-",
                    "AB+",
                    "AB-",
                    "Desconocido",
                ],
                "required": False,
            },
        ],
    },
    "consultation_reason": {
        "title": "Motivo de consulta",
        "subtitle": "Explica qué síntomas tienes o cómo te sientes.",
        "fields": [
            {
                "key": "reason",
                "label": "Motivo de consulta",
                "type": "long_text",
                "required": True,
                "placeholder": "Ej. Dolor de cabeza desde hace 3 días, mareo, cansancio…",
            },
        ],
    },
    "allergies": {
        "title": "Alergias",
        "subtitle": "Medicamentos, alimentos u otras sustancias.",
        "fields": [
            {
                "key": "allergy_items",
                "label": "Alergias conocidas",
                "type": "allergy_list",
                "required": False,
                "placeholder": "Ej. Penicilina, polen, mariscos…",
            },
        ],
    },
    "medications": {
        "title": "Medicamentos actuales",
        "subtitle": "Agrega cada medicamento por separado.",
        "fields": [
            {
                "key": "medication_items",
                "label": "Medicamentos que tomas",
                "type": "medication_list",
                "required": False,
            },
        ],
    },
    "family_history": {
        "title": "Antecedentes familiares",
        "subtitle": "Agrega cada antecedente por separado.",
        "fields": [
            {
                "key": "family_history_items",
                "label": "Antecedentes familiares",
                "type": "family_history_list",
                "required": False,
            },
        ],
    },
    "surgeries": {
        "title": "Cirugías previas",
        "subtitle": "Agrega cada cirugía u hospitalización por separado.",
        "fields": [
            {
                "key": "surgery_items",
                "label": "Cirugías o hospitalizaciones previas",
                "type": "surgery_list",
                "required": False,
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
    "weight_kg": "weight_kg",
    "blood_type": "blood_type",
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
        if sid == "consultation_reason":
            illness_block = saved.get("current_illness")
            if isinstance(illness_block, dict):
                legacy_illness = illness_block.get("current_illness")
                if legacy_illness and not section_saved.get("reason"):
                    section_saved = {**section_saved, "reason": legacy_illness}
        if sid == "allergies" and "allergy_items" not in section_saved:
            legacy = section_saved.get("allergies")
            if isinstance(legacy, str) and legacy.strip():
                low = legacy.strip().lower()
                section_saved = {
                    **section_saved,
                    "allergy_items": []
                    if low in ("ninguna", "ninguno", "no", "n/a")
                    else [legacy.strip()],
                }
        if sid == "medications" and "medication_items" not in section_saved:
            legacy = section_saved.get("medications")
            if isinstance(legacy, str) and legacy.strip():
                low = legacy.strip().lower()
                section_saved = {
                    **section_saved,
                    "medication_items": []
                    if low in ("ninguno", "ninguna", "no", "n/a")
                    else [{"name": legacy.strip(), "mg": ""}],
                }
        if sid == "family_history" and "family_history_items" not in section_saved:
            legacy = section_saved.get("family_history")
            if isinstance(legacy, str) and legacy.strip():
                low = legacy.strip().lower()
                section_saved = {
                    **section_saved,
                    "family_history_items": []
                    if low in ("ninguno", "ninguna", "no", "n/a", "ninguna reportada")
                    else [{"condition": legacy.strip(), "relative": ""}],
                }
        if sid == "surgeries" and "surgery_items" not in section_saved:
            legacy = section_saved.get("surgeries")
            if isinstance(legacy, str) and legacy.strip():
                low = legacy.strip().lower()
                section_saved = {
                    **section_saved,
                    "surgery_items": []
                    if low in ("ninguno", "ninguna", "no", "n/a", "ninguna")
                    else [{"procedure": legacy.strip(), "date": ""}],
                }
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
    saved = saved_responses if isinstance(saved_responses, dict) else {}

    # Cada paso del wizard debe guardarse al menos una vez (aunque sea opcional).
    for section in sections:
        sid = section.get("id")
        if sid and sid not in saved:
            return False

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
            ftype = field.get("type") or ""
            if ftype in (
                "allergy_list",
                "medication_list",
                "family_history_list",
                "surgery_list",
            ):
                if not isinstance(val, list):
                    return False
                non_empty = [
                    v
                    for v in val
                    if (isinstance(v, str) and v.strip())
                    or (
                        isinstance(v, dict)
                        and (
                            str(v.get("name") or "").strip()
                            or str(v.get("condition") or "").strip()
                            or str(v.get("procedure") or "").strip()
                        )
                    )
                ]
                if not non_empty:
                    return False
                continue
            if ftype == "phone" or key == "phone":
                digits = "".join(c for c in str(val or "") if c.isdigit())
                if len(digits) != 10:
                    return False
                continue
            if val is None or (isinstance(val, str) and not val.strip()):
                return False
    return True


def _format_field_value_for_display(key: str, field_type: str, value: Any) -> str:
    if key == "allergy_items" or field_type == "allergy_list":
        if not isinstance(value, list):
            return _field_value_to_str(value)
        items = [str(v).strip() for v in value if str(v).strip()]
        return ", ".join(items) if items else "Ninguna reportada"
    if key == "medication_items" or field_type == "medication_list":
        if not isinstance(value, list):
            return _field_value_to_str(value)
        parts: List[str] = []
        for item in value:
            if isinstance(item, dict):
                name = str(item.get("name") or "").strip()
                mg = str(item.get("mg") or "").strip()
                if name:
                    parts.append(f"{name} {mg} mg".strip() if mg else name)
            elif item:
                parts.append(str(item).strip())
        return ", ".join(parts) if parts else "Ninguno reportado"
    if key == "family_history_items" or field_type == "family_history_list":
        if not isinstance(value, list):
            return _field_value_to_str(value)
        parts: List[str] = []
        for item in value:
            if isinstance(item, dict):
                condition = str(item.get("condition") or "").strip()
                relative = str(item.get("relative") or "").strip()
                if condition:
                    parts.append(
                        f"{condition} ({relative})".strip()
                        if relative
                        else condition
                    )
            elif item:
                parts.append(str(item).strip())
        return ", ".join(parts) if parts else "Ninguno reportado"
    if key == "surgery_items" or field_type == "surgery_list":
        if not isinstance(value, list):
            return _field_value_to_str(value)
        parts: List[str] = []
        for item in value:
            if isinstance(item, dict):
                procedure = str(item.get("procedure") or "").strip()
                date = str(item.get("date") or "").strip()
                if procedure:
                    parts.append(f"{procedure} ({date})".strip() if date else procedure)
            elif item:
                parts.append(str(item).strip())
        return ", ".join(parts) if parts else "Ninguna reportada"
    return _field_value_to_str(value)


def _field_value_to_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ", ".join(str(v) for v in value if v is not None)
    return str(value).strip()


def build_clinical_intake_detail_sections(
    intake_context: Optional[Dict[str, Any]],
    saved_responses: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Vista de solo lectura para el médico (timeline / detalle)."""
    sections_raw = build_intake_sections_for_invitation(
        intake_context, saved_responses
    )
    saved = saved_responses or {}
    out: List[Dict[str, Any]] = []
    for section in sections_raw:
        sid = section.get("id") or ""
        section_saved = saved.get(sid) if isinstance(saved.get(sid), dict) else {}
        fields_out = []
        for field in section.get("fields") or []:
            key = field.get("key") or ""
            ftype = field.get("type") or ""
            raw = section_saved.get(key)
            if raw is None:
                raw = field.get("value")
            val = _format_field_value_for_display(key, ftype, raw)
            if ftype in (
                "allergy_list",
                "medication_list",
                "family_history_list",
                "surgery_list",
            ):
                fields_out.append(
                    {
                        "key": key,
                        "label": field.get("label") or key,
                        "value": val,
                    }
                )
                continue
            if not val:
                continue
            fields_out.append(
                {
                    "key": key,
                    "label": field.get("label") or field.get("key") or "",
                    "value": val,
                }
            )
        if fields_out:
            out.append(
                {
                    "id": section.get("id") or "",
                    "title": section.get("title") or "",
                    "subtitle": section.get("subtitle"),
                    "fields": fields_out,
                }
            )
    return out


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
