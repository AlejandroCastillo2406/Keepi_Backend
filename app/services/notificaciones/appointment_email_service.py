from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

from app.core.config import settings
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


def build_public_appointment_response_link(raw_token: str, action: str) -> str:
    base = (settings.public_questionnaire_base_url or "").strip().rstrip("/")
    if not base:
        return raw_token
    safe_action = "confirmar" if action == "accept" else "cancelar"
    return f"{base}/cita/{raw_token}?accion={safe_action}"


def build_doctor_scheduled_appointment_email_html(
    *,
    patient_name: str,
    doctor_name: str,
    reason: str,
    when_label: str,
    confirmed_from_web: bool = False,
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

    intro = (
        f"{_format_doctor_display(doctor_name)} confirmó tu cita."
        if confirmed_from_web
        else f"{_format_doctor_display(doctor_name)} programó una consulta contigo."
    )

    return build_clinical_action_email_html(
        patient_name=patient_name,
        doctor_name=doctor_name,
        headline="Tu cita está confirmada",
        body_paragraphs=[
            intro,
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


def build_appointment_proposal_email_html(
    *,
    patient_name: str,
    doctor_name: str,
    reason: str,
    when_label: str,
    confirm_link: str,
    reject_link: str,
) -> str:
    safe_reason = escape((reason or "Consulta médica").strip(), quote=True)
    safe_when = escape(when_label.strip(), quote=True)
    highlight = f"""
      <div style="margin:0 0 4px;padding:16px;border-radius:12px;background:#F8FAFC;
        border:1px solid #E2E8F0;">
        <p style="margin:0 0 10px;font-size:11px;font-weight:700;letter-spacing:0.05em;
          text-transform:uppercase;color:#64748B;">Nueva propuesta</p>
        <p style="margin:0 0 8px;font-size:14px;line-height:1.55;color:#334155;">
          <strong>Fecha y hora:</strong> {safe_when}
        </p>
        <p style="margin:0;font-size:14px;line-height:1.55;color:#334155;">
          <strong>Motivo:</strong> {safe_reason}
        </p>
      </div>"""

    return build_clinical_action_email_html(
        patient_name=patient_name,
        doctor_name=doctor_name,
        headline="Confirma tu nueva cita",
        body_paragraphs=[
            f"{_format_doctor_display(doctor_name)} te propone un nuevo horario para tu consulta.",
            "Responde con uno de los botones de abajo. Una vez confirmada o rechazada, los botones dejarán de estar disponibles.",
        ],
        cta_label="Confirmar cita",
        cta_href=confirm_link,
        secondary_cta_label="Rechazar cita",
        secondary_cta_href=reject_link,
        footer_note="Si el enlace no funciona, abre la app Keepi para gestionar la cita.",
        highlight_box_html=highlight,
        badge_subtitle="Propuesta de cita",
    )


def build_appointment_rejection_email_html(
    *,
    patient_name: str,
    doctor_name: str,
    reason: str,
    when_label: str,
    scheduling_link: str,
) -> str:
    safe_reason = escape((reason or "Consulta médica").strip(), quote=True)
    safe_when = escape(when_label.strip(), quote=True)
    safe_link = escape(scheduling_link, quote=True)
    highlight = f"""
      <div style="margin:0 0 4px;padding:16px;border-radius:12px;background:#F8FAFC;
        border:1px solid #E2E8F0;">
        <p style="margin:0 0 10px;font-size:11px;font-weight:700;letter-spacing:0.05em;
          text-transform:uppercase;color:#64748B;">Solicitud no confirmada</p>
        <p style="margin:0 0 8px;font-size:14px;line-height:1.55;color:#334155;">
          <strong>Fecha solicitada:</strong> {safe_when}
        </p>
        <p style="margin:0;font-size:14px;line-height:1.55;color:#334155;">
          <strong>Motivo:</strong> {safe_reason}
        </p>
      </div>"""

    scheduling_block = ""
    if scheduling_link.startswith("http"):
        scheduling_block = f"""
      <div style="margin:24px 0 0;padding:18px;border-radius:12px;background:#F0F9FF;
        border:1px solid #BAE6FD;">
        <p style="margin:0 0 8px;font-size:14px;font-weight:700;color:#0C4A6E;">
          Agenda cuando quieras
        </p>
        <p style="margin:0 0 14px;font-size:14px;line-height:1.55;color:#0369A1;">
          Este enlace es personal y puedes usarlo cuando desees solicitar una nueva cita.
        </p>
        <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%">
          <tr>
            <td align="center">
              <a href="{safe_link}" target="_blank"
                style="display:inline-block;background:#0284C7;color:#ffffff;
                  text-decoration:none;font-size:14px;font-weight:600;
                  padding:12px 24px;border-radius:50px;text-align:center;">
                Agendar una cita
              </a>
            </td>
          </tr>
        </table>
      </div>"""

    html = build_clinical_action_email_html(
        patient_name=patient_name,
        doctor_name=doctor_name,
        headline="Tu solicitud de cita no fue confirmada",
        body_paragraphs=[
            f"{_format_doctor_display(doctor_name)} no pudo confirmar la cita que solicitaste.",
            "Puedes elegir otro horario cuando lo desees usando el enlace de abajo.",
        ],
        cta_label=(
            "Agendar una cita" if scheduling_link.startswith("http") else ""
        ),
        cta_href=scheduling_link if scheduling_link.startswith("http") else "",
        footer_note=(
            "Si tienes dudas, contacta directamente a tu médico."
        ),
        highlight_box_html=highlight + scheduling_block,
        badge_subtitle="Solicitud de cita",
    )
    return html


def send_doctor_scheduled_appointment_email(
    *,
    to_email: str,
    patient_name: str,
    doctor_name: str,
    reason: str,
    when_label: str,
    confirmed_from_web: bool = False,
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
        confirmed_from_web=confirmed_from_web,
    )
    result = send_simple_html_email_ses(email, subject, html)
    return AppointmentEmailResult(
        success=result.success,
        error=result.error,
        ses_message_id=result.ses_message_id,
    )


def send_appointment_proposal_email(
    *,
    to_email: str,
    patient_name: str,
    doctor_name: str,
    reason: str,
    when_label: str,
    confirm_link: str,
    reject_link: str,
) -> AppointmentEmailResult:
    email = (to_email or "").strip()
    if not email:
        return AppointmentEmailResult(success=False, error="Paciente sin correo")

    subject = f"Confirma tu cita con {_format_doctor_display(doctor_name)}"
    html = build_appointment_proposal_email_html(
        patient_name=patient_name,
        doctor_name=doctor_name,
        reason=reason,
        when_label=when_label,
        confirm_link=confirm_link,
        reject_link=reject_link,
    )
    result = send_simple_html_email_ses(email, subject, html)
    return AppointmentEmailResult(
        success=result.success,
        error=result.error,
        ses_message_id=result.ses_message_id,
    )


def send_appointment_rejection_email(
    *,
    to_email: str,
    patient_name: str,
    doctor_name: str,
    reason: str,
    when_label: str,
    scheduling_link: str,
) -> AppointmentEmailResult:
    email = (to_email or "").strip()
    if not email:
        return AppointmentEmailResult(success=False, error="Paciente sin correo")

    subject = (
        f"Tu solicitud de cita con {_format_doctor_display(doctor_name)} "
        "no fue confirmada"
    )
    html = build_appointment_rejection_email_html(
        patient_name=patient_name,
        doctor_name=doctor_name,
        reason=reason,
        when_label=when_label,
        scheduling_link=scheduling_link,
    )
    result = send_simple_html_email_ses(email, subject, html)
    return AppointmentEmailResult(
        success=result.success,
        error=result.error,
        ses_message_id=result.ses_message_id,
    )
