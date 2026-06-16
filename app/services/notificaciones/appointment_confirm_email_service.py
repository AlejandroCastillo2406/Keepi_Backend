from html import escape as html_escape

from app.core.config import settings
from app.services.notificaciones.clinical_email_layout import (
    _format_doctor_display,
    build_clinical_action_email_html,
)
from app.services.notificaciones.payment_email_service import (
    PaymentEmailResult,
    send_simple_html_email_ses,
)


def build_public_appointment_response_link(raw_token: str, action: str) -> str:
    base = (settings.public_questionnaire_base_url or "").strip().rstrip("/")
    token = (raw_token or "").strip()
    if not base or not token:
        return ""
    action_slug = "confirmar" if action == "accept" else "cancelar"
    return f"{base}/cita/{token}?accion={action_slug}"


def build_public_appointment_response_page_link(raw_token: str) -> str:
    base = (settings.public_questionnaire_base_url or "").strip().rstrip("/")
    token = (raw_token or "").strip()
    if not base or not token:
        return ""
    return f"{base}/cita/{token}"


def build_appointment_confirm_email_subject(doctor_name: str) -> str:
    brand = (getattr(settings, "email_brand_name", "") or "").strip()
    if brand.startswith("http"):
        brand = "Keepi"
    brand = brand or "Keepi"
    doctor = _format_doctor_display(doctor_name)
    return f"{brand} – {doctor} te propuso una cita"


def build_appointment_confirm_email_html(
    *,
    patient_name: str,
    doctor_name: str,
    reason: str,
    when_label: str,
    confirm_link: str,
    cancel_link: str,
) -> str:
    reason_text = (reason or "").strip() or "Consulta médica"
    safe_reason = html_escape(reason_text, quote=True)
    safe_when = html_escape(when_label, quote=True)
    highlight = f"""
      <div style="margin:0 0 20px;padding:14px 16px;border-radius:10px;
        background:#F8FAFC;border:1px solid #E2E8F0;">
        <p style="margin:0 0 6px;font-size:11px;font-weight:700;letter-spacing:0.05em;
          text-transform:uppercase;color:#64748B;">Detalle de la cita</p>
        <p style="margin:0 0 10px;font-size:14px;line-height:1.55;color:#334155;">
          <strong>Fecha y hora:</strong> {safe_when}
        </p>
        <p style="margin:0;font-size:14px;line-height:1.55;color:#334155;">
          <strong>Motivo:</strong> {safe_reason}
        </p>
      </div>"""

    has_links = confirm_link.startswith("http") and cancel_link.startswith("http")
    body_paragraphs = [
        f"{_format_doctor_display(doctor_name)} programó una cita contigo.",
        "Confirma o cancela con los botones de abajo. También puedes hacerlo desde la app Keepi.",
    ]
    if not has_links:
        body_paragraphs.append(
            "Abre la app Keepi para revisar la propuesta en tus notificaciones."
        )

    return build_clinical_action_email_html(
        patient_name=patient_name,
        doctor_name=doctor_name,
        headline="Confirma tu cita médica",
        body_paragraphs=body_paragraphs,
        cta_label="Confirmar cita" if has_links else "",
        cta_href=confirm_link if has_links else "",
        secondary_cta_label="Cancelar cita" if has_links else "",
        secondary_cta_href=cancel_link if has_links else "",
        footer_note=(
            "Una vez confirmes o canceles, los botones dejarán de estar disponibles."
            if has_links
            else "Si no ves la propuesta en la app, pídele a tu médico que la reenvíe."
        ),
        highlight_box_html=highlight,
        badge_subtitle="Propuesta de cita",
    )


def send_appointment_confirm_email(
    *,
    to_email: str,
    patient_name: str,
    doctor_name: str,
    reason: str,
    when_label: str,
    confirm_link: str,
    cancel_link: str,
) -> PaymentEmailResult:
    if not (to_email or "").strip():
        return PaymentEmailResult(success=False, error="Correo del paciente vacío")
    subject = build_appointment_confirm_email_subject(doctor_name)
    html = build_appointment_confirm_email_html(
        patient_name=patient_name,
        doctor_name=doctor_name,
        reason=reason,
        when_label=when_label,
        confirm_link=confirm_link,
        cancel_link=cancel_link,
    )
    return send_simple_html_email_ses(to_email.strip(), subject, html)
