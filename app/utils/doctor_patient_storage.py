"""Rutas de almacenamiento del doctor: {paciente}/Analisis y {paciente}/Recetas."""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Optional

_ANALYSIS_SUBFOLDER = "Analisis"
_PRESCRIPTION_SUBFOLDER = "Recetas"


def sanitize_storage_segment(name: str, *, max_len: int = 50) -> str:
    raw = (name or "").strip() or "paciente"
    normalized = unicodedata.normalize("NFD", raw)
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    if not ascii_name.strip():
        ascii_name = raw
    sanitized = re.sub(r"[^a-zA-Z0-9\-_]", "_", ascii_name)
    sanitized = re.sub(r"_+", "_", sanitized).strip("_")
    return (sanitized[:max_len] or "paciente")


def patient_folder_label(user: Optional[Any]) -> str:
    if user is None:
        return "paciente"
    label = (
        getattr(user, "name", None)
        or getattr(user, "email", None)
        or str(getattr(user, "id", "") or "")
    )
    return (label or "").strip() or "paciente"


def doctor_patient_analysis_folder(patient_name: str) -> str:
    return f"{sanitize_storage_segment(patient_name)}/{_ANALYSIS_SUBFOLDER}"


def doctor_patient_prescription_folder(patient_name: str) -> str:
    return f"{sanitize_storage_segment(patient_name)}/{_PRESCRIPTION_SUBFOLDER}"


def sanitize_s3_relative_path(path: str) -> str:
    """Sanitiza cada segmento de una ruta S3 relativa (preserva '/')."""
    parts = [p.strip() for p in (path or "").replace("\\", "/").split("/") if p.strip()]
    if not parts:
        return "other"
    return "/".join(sanitize_storage_segment(p) for p in parts)
