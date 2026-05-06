from html import escape as html_escape
from datetime import datetime, timezone, timedelta
from typing import Optional

from app.core.config import settings


def build_public_analysis_upload_link(raw_token: str) -> str:
    base = (settings.public_questionnaire_base_url or "").strip().rstrip("/")
    if not base:
        return raw_token
    return f"{base}/upload/{raw_token}"


def build_analysis_upload_email_html(
    *,
    patient_name: str,
    doctor_name: str,
    description: str,
    public_link: str,
    expires_at: Optional[datetime] = None,
) -> str:
    brand = (getattr(settings, "email_brand_name", "") or "").strip() or "Keepi"

    safe_name = html_escape((patient_name or "").strip() or "Hola", quote=True)
    safe_doctor = html_escape((doctor_name or "Tu doctor").strip(), quote=True)
    safe_desc = html_escape((description or "").strip(), quote=True)
    safe_href = html_escape(public_link or "", quote=True)
    safe_brand = html_escape(brand, quote=True)
    
    if expires_at is not None:
        safe_expiration_msg = html_escape(f"hasta el {expires_at.strftime('%d/%m/%Y')}", quote=True)
    else:
        safe_expiration_msg = html_escape("por 30 días", quote=True)

    logo_url = "https://raw.githubusercontent.com/AlejandroCastillo2406/Keepi_Front/master/assets/icons/logo.png"

    description_block = (
        f"""
      <div style="margin:0 0 24px;padding:14px 16px;border-radius:10px;background:#fff7ed;border:1px solid #fed7aa;color:#7c2d12;font-size:14px;line-height:1.5;">
        <strong style="display:block;margin-bottom:4px;color:#9a3412;">Detalle de la solicitud</strong>
        {safe_desc}
      </div>
        """
        if safe_desc
        else ""
    )

    return f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8" /></head>
<body style="font-family:system-ui,sans-serif;background:#f3f4f6;padding:24px;">
  <table role="presentation" width="100%" style="max-width:560px;margin:0 auto;background:#ffffff;border-radius:12px;padding:32px;box-shadow: 0 4px 6px rgba(0,0,0,0.05); border-top: 4px solid #ea580c;">
    <tr><td>

      <table role="presentation" border="0" cellpadding="0" cellspacing="0" style="margin:0 0 24px;">
        <tr>
          <td valign="middle">
            <img src="{logo_url}" alt="Icono" style="height:42px; width:auto; display:block; margin-right:12px;" />
          </td>
          <td valign="middle">
            <span style="font-size:30px; font-weight:800; color:#1e293b; font-family:system-ui,sans-serif; letter-spacing:-0.5px;">{safe_brand}</span>
          </td>
        </tr>
      </table>

      <p style="margin:0 0 12px;color:#374151;">Hola {safe_name},</p>
      <p style="margin:0 0 20px;color:#374151;">{safe_doctor} te pidió subir el resultado de un análisis. Puedes hacerlo de forma segura desde el siguiente enlace, sin necesidad de iniciar sesión.</p>

      {description_block}

      <table role="presentation" border="0" cellpadding="0" cellspacing="0" style="margin:0 0 24px;">
        <tr>
          <td align="center" bgcolor="#ea580c" style="border-radius:8px;">
            <a href="{safe_href}" target="_blank" style="font-size:15px;font-family:system-ui,sans-serif;color:#ffffff;text-decoration:none;padding:12px 24px;border:1px solid #ea580c;display:inline-block;border-radius:8px;font-weight:600;">Subir análisis</a>
          </td>
        </tr>
      </table>

      <p style="margin:0 0 8px;font-size:14px;color:#6b7280;">Este enlace estará disponible {safe_expiration_msg}.</p>
      <p style="margin:0;font-size:14px;color:#6b7280;">Si el enlace expiró o tienes problemas para abrirlo, comunícate con tu doctor para que te envíe uno nuevo.</p>
    </td></tr>
  </table>
</body></html>"""
