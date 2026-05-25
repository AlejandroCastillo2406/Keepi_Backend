from html import escape as html_escape

from app.core.config import settings
from app.services.notificaciones.clinical_email_layout import (
    _format_doctor_display,
    build_clinical_action_email_html,
)


def build_public_analysis_upload_link(raw_token: str) -> str:
    base = (settings.public_questionnaire_base_url or "").strip().rstrip("/")
    if not base:
        return raw_token
    return f"{base}/upload/{raw_token}"


def build_analysis_upload_email_subject(doctor_name: str) -> str:
    brand = (getattr(settings, "email_brand_name", "") or "").strip()
    if brand.startswith("http"):
        brand = "Keepi"
    brand = brand or "Keepi"
    doctor = _format_doctor_display(doctor_name)
    return f"{brand} – {doctor} te pidió subir un análisis"


def build_analysis_upload_email_html(
    *,
    patient_name: str,
    doctor_name: str,
    description: str,
    public_link: str,
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

    return build_clinical_action_email_html(
        patient_name=patient_name,
        doctor_name=doctor_name,
        headline="Sube el resultado de tu análisis",
        body_paragraphs=[
            f"{_format_doctor_display(doctor_name)} necesita que compartas los resultados "
            "de tu estudio. Puedes subir el archivo de forma segura con el botón de abajo, "
            "sin iniciar sesión en la app.",
        ],
        cta_label="Subir análisis",
        cta_href=public_link,
        footer_note=(
            f"Este enlace estará disponible {expires_in_days} días. "
            "Si expiró, pídele a tu médico que te envíe uno nuevo."
        ),
        highlight_box_html=highlight,
        badge_subtitle="Solicitud de análisis",
    )
