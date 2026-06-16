from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

from app.services.notificaciones.clinical_email_layout import (
    _format_doctor_display,
    build_clinical_action_email_html,
)
from app.services.notificaciones.payment_email_service import send_simple_html_email_ses


@dataclass
class AppointmentEmailResult:
    success: bool
    error: str | None = None
    ses_message_id: str | None = None


def _format_slot_range(
    start_at: datetime | None,
    end_at: datetime | None,
    *,
    timezone: str = "America/Mexico_City",
) -> str:
    if start_at is None:
        return "Por confirmar con tu médico"
    try:
        tz = ZoneInfo(timezone)
    except Exception:
        tz = ZoneInfo("America/Mexico_City")
    local_start = start_at.astimezone(tz)
    date_part = local_start.strftime("%d/%m/%Y")
    time_start = local_start.strftime("%H:%M")
    if end_at is not None:
        local_end = end_at.astimezone(tz)
        time_end = local_end.strftime("%H:%M")
        return f"{date_part} · {time_start} – {time_end}"
    return f"{date_part} · {time_start}"


def build_doctor_scheduled_appointment_email_subject(*, doctor_name: str) -> str:
    doctor = _format_doctor_display(doctor_name)
    return f"Cita confirmada con {doctor}"


def build_doctor_scheduled_appointment_email_html(
    *,
    patient_name: str,
    doctor_name: str,
    reason: str,
    when_label: str,
) -> str:
    safe_reason = escape((reason or "Consulta médica").strip(), quote=True)
    safe_when = escape(when_label.strip(), quote=True)
    highlight = f"""
      <div style="margin:0 0 4px;padding:16px;border-radius:12px;background:#F8FAFC;
        border:1px solid #E2E8F0;">
        <p style="margin:0 0 10px;font-size:11px;font-weight:700;letter-spacing:0.05em;
          text-transform:uppercase;color:#64748B;">Detalle de tu cita</p>
        <p style="margin:0 0 8px;font-size:14px;line-height:1.55;color:#334155;">
          <strong>Fecha y hora:</strong> {safe_when}
        </p>
        <p style="margin:0 0 8px;font-size:14px;line-height:1.55;color:#334155;">
          <strong>Motivo:</strong> {safe_reason}
        </p>
        <p style="margin:0;font-size:14px;line-height:1.55;color:#047857;font-weight:600;">
          Estado: confirmada
        </p>
      </div>"""

    return build_clinical_action_email_html(
        patient_name=patient_name,
        doctor_name=doctor_name,
        headline="Tu cita está confirmada",
        body_paragraphs=[
            f"{_format_doctor_display(doctor_name)} programó una consulta contigo.",
            "Guarda estos datos. Este mensaje es solo informativo; no necesitas confirmar ni cancelar desde el correo.",
        ],
        cta_label="",
        cta_href="",
        footer_note=(
            "Si necesitas reprogramar o cancelar, contacta directamente a tu médico."
        ),
        highlight_box_html=highlight,
        badge_subtitle="Cita médica confirmada",
    )


def send_doctor_scheduled_appointment_email(
    *,
    to_email: str,
    patient_name: str,
    doctor_name: str,
    reason: str,
    when_label: str,
) -> AppointmentEmailResult:
    email = (to_email or "").strip()
    if not email:
        return AppointmentEmailResult(success=False, error="Paciente sin correo")

    subject = build_doctor_scheduled_appointment_email_subject(doctor_name=doctor_name)
    html = build_doctor_scheduled_appointment_email_html(
        patient_name=patient_name,
        doctor_name=doctor_name,
        reason=reason,
        when_label=when_label,
    )
    result = send_simple_html_email_ses(email, subject, html)
    return AppointmentEmailResult(
        success=result.success,
        error=result.error,
        ses_message_id=result.ses_message_id,
    )
