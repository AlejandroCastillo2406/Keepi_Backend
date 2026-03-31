"""Envío de credenciales temporales de paciente vía SES (misma configuración que otros correos)."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import settings


@dataclass
class PatientInviteEmailResult:
    success: bool
    error: str | None = None
    ses_message_id: str | None = None


def _html(patient_name: str, email: str, temporary_password: str, brand: str) -> str:
    pn = escape(patient_name)
    em = escape(email)
    pw = escape(temporary_password)
    br = escape(brand)
    return f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8" /></head>
<body style="font-family:system-ui,sans-serif;background:#f4f4f5;padding:24px;">
  <table role="presentation" width="100%" style="max-width:560px;margin:0 auto;background:#fff;border-radius:12px;padding:32px;">
    <tr><td>
      <p style="margin:0 0 16px;font-size:18px;font-weight:600;color:#18181b;">{br}</p>
      <p style="margin:0 0 12px;color:#3f3f46;">Hola {pn},</p>
      <p style="margin:0 0 12px;color:#3f3f46;">Tu médico ha creado tu cuenta. Usuario (correo): <strong>{em}</strong></p>
      <p style="margin:0 0 8px;color:#3f3f46;">Contraseña temporal (cámbiala al iniciar sesión):</p>
      <p style="margin:0 0 20px;font-family:monospace;font-size:15px;background:#f4f4f5;padding:12px;border-radius:8px;">{pw}</p>
      <p style="margin:0;font-size:14px;color:#71717a;">Por seguridad, deberás elegir una nueva contraseña la primera vez que entres.</p>
    </td></tr>
  </table>
</body></html>"""


def send_patient_invite_email(
    to_email: str,
    patient_name: str,
    temporary_password: str,
) -> PatientInviteEmailResult:
    brand = (settings.email_brand_name or "").strip() or "Keepi"
    subject = f"Tu acceso a {brand}"
    html = _html(patient_name, to_email, temporary_password, brand)

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
        return PatientInviteEmailResult(success=True, ses_message_id=result.get("MessageId"))
    except (BotoCoreError, ClientError) as exc:
        return PatientInviteEmailResult(success=False, error=str(exc))
