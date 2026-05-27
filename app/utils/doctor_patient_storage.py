"""Rutas de almacenamiento del doctor: {paciente}/Analisis y {paciente}/Recetas."""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Any, Optional

from app.utils.storage_filename import _split_name, extension_for_content_type

_ANALYSIS_SUBFOLDER = "Analisis"
_PRESCRIPTION_SUBFOLDER = "Recetas"
_PRIOR_DOCS_SUBFOLDER = "Documentos_Previos"


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


def doctor_patient_prior_documents_folder(patient_name: str) -> str:
    return f"{sanitize_storage_segment(patient_name)}/{_PRIOR_DOCS_SUBFOLDER}"


def build_prior_document_filename(
    uploaded_at: datetime,
    *,
    content_type: str,
    original_filename: str = "",
    sequence: int = 1,
) -> str:
    """Nombre en S3: DocumentoPrevio_{YYYY-MM-DD}_{n}.ext"""
    date_str = uploaded_at.strftime("%Y-%m-%d")
    _, orig_ext = _split_name(original_filename or "")
    ext = orig_ext or extension_for_content_type(content_type or "") or ".pdf"
    if not ext.startswith("."):
        ext = f".{ext}"
    seq = max(1, int(sequence))
    return f"DocumentoPrevio_{date_str}_{seq}{ext}"


def build_analysis_result_filename(
    uploaded_at: datetime,
    *,
    analysis_description: str,
    content_type: str,
    original_filename: str = "",
) -> str:
    """Nombre en S3: Resultado_{analisis_solicitado}_{YYYY-MM-DD}.ext"""
    date_str = uploaded_at.strftime("%Y-%m-%d")
    desc = sanitize_storage_segment(
        (analysis_description or "").strip() or "analisis",
        max_len=60,
    )
    _, orig_ext = _split_name(original_filename or "")
    ext = orig_ext or extension_for_content_type(content_type or "") or ".pdf"
    if not ext.startswith("."):
        ext = f".{ext}"
    return f"Resultado_{desc}_{date_str}{ext}"


def build_receta_assigned_filename(
    assigned_at: datetime,
    *,
    content_type: str,
    original_filename: str = "",
) -> str:
    """Nombre final en S3: Receta_YYYY-MM-DD.ext según fecha de asignación."""
    date_str = assigned_at.strftime("%Y-%m-%d")
    _, orig_ext = _split_name(original_filename or "")
    ext = orig_ext or extension_for_content_type(content_type or "") or ".pdf"
    if not ext.startswith("."):
        ext = f".{ext}"
    return f"Receta_{date_str}{ext}"


def sanitize_s3_relative_path(path: str) -> str:
    """Sanitiza cada segmento de una ruta S3 relativa (preserva '/')."""
    parts = [p.strip() for p in (path or "").replace("\\", "/").split("/") if p.strip()]
    if not parts:
        return "other"
    return "/".join(sanitize_storage_segment(p) for p in parts)
