from __future__ import annotations

from dataclasses import dataclass
from html import escape

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import settings
from app.services.notificaciones.clinical_email_layout import (
    _brand,
    _format_doctor_display,
    build_clinical_action_email_html,
)


@dataclass
class PatientInviteEmailResult:
    success: bool
    error: str | None = None
    ses_message_id: str | None = None


def _html(
    patient_name: str,
    email: str,
    temporary_password: str,
    doctor_name: str | None,
) -> str:
    doctor = _format_doctor_display(doctor_name or "Tu médico")
    cred_block = f"""
      <div style="margin:0 0 20px;padding:16px;border-radius:10px;background:#F8FAFC;
        border:1px solid #E2E8F0;">
        <p style="margin:0 0 8px;font-size:13px;color:#64748B;">Usuario (correo)</p>
        <p style="margin:0 0 14px;font-size:15px;font-weight:600;color:#111827;">{escape(email)}</p>
        <p style="margin:0 0 8px;font-size:13px;color:#64748B;">Contraseña temporal</p>
        <p style="margin:0;font-family:ui-monospace,monospace;font-size:15px;
          color:#111827;letter-spacing:0.02em;">{escape(temporary_password)}</p>
      </div>
      <p style="margin:0;font-size:14px;color:#6B7280;">
        Por seguridad, deberás elegir una nueva contraseña la primera vez que entres a la app.
      </p>"""
    return build_clinical_action_email_html(
        patient_name=patient_name,
        doctor_name=doctor_name or "Tu médico",
        headline="Tu cuenta en Keepi está lista",
        body_paragraphs=[
            f"{doctor} creó tu cuenta de paciente. Usa estos datos para iniciar sesión en la app:",
        ],
        cta_label="Ir a Keepi",
        cta_href=(settings.email_link_account or "https://keepi.onrender.com").strip(),
        footer_note="No compartas tu contraseña temporal con nadie.",
        highlight_box_html=cred_block,
        badge_subtitle="Invitación de tu médico",
    )


def send_patient_invite_email(
    to_email: str,
    patient_name: str,
    temporary_password: str,
    *,
    doctor_name: str | None = None,
) -> PatientInviteEmailResult:
    brand = _brand()
    doctor = _format_doctor_display(doctor_name or "Tu médico")
    subject = f"{brand} – {doctor} te dio acceso a la app"
    html = _html(patient_name, to_email, temporary_password, doctor_name)

    source_email = settings.ses_from_email
    source_name = settings.ses_from_name
    if not source_email:
        return PatientInviteEmailResult(
            success=False,
            error="SES_FROM_EMAIL no configurado; no se puede enviar el correo de invitación.",
        )

    client = boto3.client(
        "ses",
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )

    try:
        result = client.send_email(
            Source=f"{source_name} <{source_email}>",
            Destination={"ToAddresses": [to_email]},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {"Html": {"Data": html, "Charset": "UTF-8"}},
            },
        )
        return PatientInviteEmailResult(
            success=True, ses_message_id=result.get("MessageId")
        )
    except (BotoCoreError, ClientError) as exc:
        return PatientInviteEmailResult(success=False, error=str(exc))
