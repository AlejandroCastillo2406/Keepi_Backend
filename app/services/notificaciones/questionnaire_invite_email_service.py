from html import escape as html_escape

from app.core.config import settings
from app.services.notificaciones.payment_email_service import send_simple_html_email_ses


def build_public_questionnaire_link(raw_token: str) -> str:
    base = (settings.public_questionnaire_base_url or "").strip().rstrip("/")
    if not base:
        return raw_token
    return f"{base}/q/{raw_token}"


def send_questionnaire_invite_email(*, to_email: str, patient_name: str, public_link: str):
    brand = (getattr(settings, "email_brand_name", "") or "").strip() or "Keepi"
    subject = f"{brand} - Cuestionario de salud"
    
    safe_name = html_escape(patient_name or "", quote=True)
    safe_href = html_escape(public_link or "", quote=True)
    safe_brand = html_escape(brand, quote=True)
    
    # URL pública del logo en GitHub
    logo_url = "https://raw.githubusercontent.com/AlejandroCastillo2406/Keepi_Front/master/assets/icons/logo.png"
    
    html = f"""<!DOCTYPE html>
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
      <p style="margin:0 0 20px;color:#374151;">Tu doctor te compartió un cuestionario de salud. Ábrelo en el siguiente enlace:</p>
      
      <table role="presentation" border="0" cellpadding="0" cellspacing="0" style="margin:0 0 24px;">
        <tr>
          <td align="center" bgcolor="#2563eb" style="border-radius:8px;">
            <a href="{safe_href}" target="_blank" style="font-size:15px;font-family:system-ui,sans-serif;color:#ffffff;text-decoration:none;padding:12px 24px;border:1px solid #2563eb;display:inline-block;border-radius:8px;font-weight:600;">Completar cuestionario</a>
          </td>
        </tr>
      </table>

      <p style="margin:0;font-size:14px;color:#6b7280;">Si el enlace expiró, solicita uno nuevo a tu doctor.</p>
    </td></tr>
  </table>
</body></html>"""

    return send_simple_html_email_ses(to_email, subject, html)