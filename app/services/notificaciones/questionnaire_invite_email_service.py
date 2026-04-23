from app.core.config import settings
from app.services.notificaciones.payment_email_service import send_simple_html_email_ses


def build_public_questionnaire_link(raw_token: str) -> str:
    base = (settings.public_questionnaire_base_url or "").strip().rstrip("/")
    if not base:
        return raw_token
    return f"{base}/q/{raw_token}"


def send_questionnaire_invite_email(*, to_email: str, patient_name: str, public_link: str):
    subject = "Keepi - Cuestionario de salud"
    html = f"""
    <div style='font-family: Arial, sans-serif; color: #1d2939;'>
      <h2>Cuestionario de salud</h2>
      <p>Hola {patient_name},</p>
      <p>Tu doctor te compartió un cuestionario de salud. Ábrelo en el siguiente enlace:</p>
      <p><a href=\"{public_link}\">Completar cuestionario</a></p>
      <p>Si el enlace expiró, solicita uno nuevo a tu doctor.</p>
    </div>
    """
    return send_simple_html_email_ses(to_email, subject, html)
