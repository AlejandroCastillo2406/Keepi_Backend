from __future__ import annotations

from datetime import datetime, timedelta, timezone
from html import escape as html_escape

from app.core.config import settings
from app.services.notificaciones.clinical_email_layout import (
    _format_doctor_display,
    build_clinical_action_email_html,
)


def build_public_analysis_upload_link(raw_token: str) -> str:
    base = (settings.public_questionnaire_base_url or "").strip().rstrip("/")
    if not base:
        return ""
    token = (raw_token or "").strip()
    if not token:
        return ""
    return f"{base}/upload/{token}"


def build_analysis_upload_email_subject(doctor_name: str) -> str:
    brand = (getattr(settings, "email_brand_name", "") or "").strip()
    if brand.startswith("http"):
        brand = "Keepi"
    brand = brand or "Keepi"
    doctor = _format_doctor_display(doctor_name)
    return f"{brand} – {doctor} te pidió subir un análisis"


def _format_deadline_label(expires_at: datetime) -> str:
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at.strftime("%d/%m/%Y")


def build_analysis_upload_email_html(
    *,
    patient_name: str,
    doctor_name: str,
    description: str,
    public_link: str,
    expires_at: datetime | None = None,
    expires_in_days: int = 30,
) -> str:
    desc = (description or "").strip()
    highlight = ""
    if desc:
        safe_desc = html_escape(desc, quote=True)
        highlight = f"""
      <div style="margin:0 0 20px;padding:14px 16px;border-radius:10px;
        background:#F8FAFC;border:1px solid #E2E8F0;">
        <p style="margin:0 0 6px;font-size:11px;font-weight:700;letter-spacing:0.05em;
          text-transform:uppercase;color:#64748B;">Detalle de la solicitud</p>
        <p style="margin:0;font-size:14px;line-height:1.55;color:#334155;">{safe_desc}</p>
      </div>"""

    if expires_at is not None:
        deadline_label = _format_deadline_label(expires_at)
        safe_deadline = html_escape(deadline_label, quote=True)
        highlight += f"""
      <div style="margin:0 0 20px;padding:14px 16px;border-radius:10px;
        background:#FFF7ED;border:1px solid #FDBA74;">
        <p style="margin:0 0 6px;font-size:11px;font-weight:700;letter-spacing:0.05em;
          text-transform:uppercase;color:#C2410C;">Fecha límite de entrega</p>
        <p style="margin:0;font-size:18px;font-weight:800;line-height:1.3;color:#9A3412;">
          {safe_deadline}
        </p>
      </div>"""

    link = (public_link or "").strip()
    has_web_link = link.startswith("http")
    body_paragraphs = [
        f"{_format_doctor_display(doctor_name)} necesita que compartas los resultados "
        "de tu estudio."
    ]
    if expires_at is not None:
        body_paragraphs.append(
            f"Por favor sube el archivo antes del {_format_deadline_label(expires_at)}."
        )
    if has_web_link:
        body_paragraphs.append(
            "Puedes subir el archivo de forma segura con el botón de abajo, "
            "sin iniciar sesión en la app."
        )
    else:
        body_paragraphs.append(
            "Abre la app Keepi en tu teléfono y revisa la sección de análisis "
            "para subir el archivo."
        )

    if expires_at is not None:
        deadline_label = _format_deadline_label(expires_at)
        footer_note = (
            f"Recuerda entregar tu estudio antes del {deadline_label}. "
            "Si el enlace expiró, pídele a tu médico que te envíe uno nuevo."
            if has_web_link
            else (
                f"Fecha límite: {deadline_label}. "
                "Si no ves la solicitud en la app, pídele a tu médico que la reenvíe."
            )
        )
    else:
        footer_note = (
            f"Este enlace estará disponible {expires_in_days} días. "
            "Si expiró, pídele a tu médico que te envíe uno nuevo."
            if has_web_link
            else "Si no ves la solicitud en la app, pídele a tu médico que la reenvíe."
        )

    return build_clinical_action_email_html(
        patient_name=patient_name,
        doctor_name=doctor_name,
        headline="Sube el resultado de tu análisis",
        body_paragraphs=body_paragraphs,
        cta_label="Subir análisis" if has_web_link else "",
        cta_href=link if has_web_link else "",
        footer_note=footer_note,
        highlight_box_html=highlight,
        badge_subtitle="Solicitud de análisis",
    )
