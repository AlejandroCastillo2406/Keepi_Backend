"""Nombre y MIME coherentes al guardar documentos (evitar imágenes como .pdf)."""
from __future__ import annotations

import mimetypes
import re
from typing import Optional, Tuple

_PDF_MAGIC = b"%PDF-"
_JPEG_MAGIC = (b"\xff\xd8\xff",)
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_GIF_MAGICS = (b"GIF87a", b"GIF89a")
_WEBP_RIFF = b"RIFF"
_WEBP_MAGIC = b"WEBP"


def sniff_content_type(file_data: bytes, declared: Optional[str] = None) -> Optional[str]:
    if file_data:
        if file_data.startswith(_PDF_MAGIC):
            return "application/pdf"
        if any(file_data.startswith(m) for m in _JPEG_MAGIC):
            return "image/jpeg"
        if file_data.startswith(_PNG_MAGIC):
            return "image/png"
        if any(file_data.startswith(m) for m in _GIF_MAGICS):
            return "image/gif"
        if (
            len(file_data) >= 12
            and file_data[:4] == _WEBP_RIFF
            and file_data[8:12] == _WEBP_MAGIC
        ):
            return "image/webp"
    if declared and declared.strip():
        return declared.strip().lower()
    return None


def extension_for_content_type(content_type: str) -> str:
    ct = (content_type or "").lower().strip()
    mapping = {
        "application/pdf": ".pdf",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }
    if ct in mapping:
        return mapping[ct]
    guessed = mimetypes.guess_extension(ct)
    return guessed or ""


def _split_name(filename: str) -> Tuple[str, str]:
    name = (filename or "").strip()
    if not name or "." not in name:
        return name, ""
    base, ext = name.rsplit(".", 1)
    return base, f".{ext.lower()}" if ext else ""


def resolve_storage_filename(
    original_filename: str,
    recommended_name: str,
    content_type: str,
    file_data: Optional[bytes] = None,
) -> Tuple[str, str]:
    """
    Devuelve (nombre_para_guardar, content_type_normalizado).
    Prioriza el tipo real del archivo (magic bytes) sobre la extensión sugerida por IA.
    """
    detected = sniff_content_type(file_data or b"", content_type) or (
        content_type or "application/octet-stream"
    ).lower()
    correct_ext = extension_for_content_type(detected)

    orig_base, orig_ext = _split_name(original_filename)
    rec = (recommended_name or "").strip() or original_filename
    rec_base, rec_ext = _split_name(rec)

    base = rec_base or orig_base or "documento"
    base = re.sub(r'[<>:"/\\|?*]', "", base).strip() or "documento"

    ext = correct_ext or orig_ext or rec_ext or ""
    if detected.startswith("image/"):
        if not ext or ext == ".pdf":
            ext = orig_ext if orig_ext and orig_ext != ".pdf" else correct_ext or ".jpg"
    elif detected == "application/pdf":
        ext = ".pdf"
    elif not ext:
        ext = extension_for_content_type(detected) or orig_ext or ".bin"

    if not ext.startswith("."):
        ext = f".{ext}"

    save_name = f"{base}{ext}"
    return save_name, detected
