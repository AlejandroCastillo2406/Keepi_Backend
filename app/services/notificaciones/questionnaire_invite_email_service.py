from typing import Optional
from app.core.config import settings
from app.services.notificaciones.clinical_email_layout import (
    _brand,
    _format_doctor_display,
    build_clinical_action_email_html,
)
from app.services.notificaciones.payment_email_service import send_simple_html_email_ses


def build_public_questionnaire_link(raw_token: str) -> str:
    base = (settings.public_questionnaire_base_url or "").strip().rstrip("/")
    if not base:
        return raw_token
    return f"{base}/q/{raw_token}"


def build_questionnaire_invite_email_subject(doctor_name: str, has_first_appointment: bool = False) -> str:
    doctor = _format_doctor_display(doctor_name)
    if has_first_appointment:
        return f"{_brand()} – Preparación para tu consulta con {doctor}"
    return f"{_brand()} – {doctor} te envió un cuestionario"


def build_questionnaire_invite_email_html(
    *,
    patient_name: str,
    doctor_name: str,
    public_link: str,
    is_dynamic: bool = False,
    first_appointment_link: Optional[str] = None,
) -> str:
    doctor = _format_doctor_display(doctor_name)
    paragraphs = []

    if is_dynamic:
        paragraphs.extend([
            f"{doctor} te invitó a un cuestionario de salud personalizado con IA. "
            "Cada pregunta se adapta a tus respuestas anteriores (máximo 10 preguntas).",
        ])
        headline = "Preparación y Cuestionario" if first_appointment_link else "Cuestionario dinámico de salud"
        badge = "Cuestionario con IA"
    else:
        paragraphs.extend([
            f"{doctor} te invitó a completar un cuestionario de salud. "
            "Tus respuestas ayudan a preparar mejor tu atención médica.",
        ])
        headline = "Preparación para tu consulta" if first_appointment_link else "Cuestionario de salud"
        badge = "Cuestionario de salud"

    # Texto directo, al grano y SIN código HTML
    if first_appointment_link:
        paragraphs.append(
            "Además del cuestionario, tu médico ha habilitado un espacio seguro "
            "para que subas tus recetas o documentos médicos previos antes de tu cita."
        )

    paragraphs.append("Usa los botones inferiores para completar tu preparación desde tu celular o computadora.")

    # Pasamos los dos enlaces a la plantilla maestra para que ella dibuje los botones
    return build_clinical_action_email_html(
        patient_name=patient_name,
        doctor_name=doctor_name,
        headline=headline,
        body_paragraphs=paragraphs,
        cta_label="Completar cuestionario",
        cta_href=public_link,
        secondary_cta_label="Subir documentos previos" if first_appointment_link else "",
        secondary_cta_href=first_appointment_link or "",
        footer_note="Si el enlace expiró, solicita uno nuevo a tu médico.",
        badge_subtitle=badge,
    )


def send_questionnaire_invite_email(
    *,
    to_email: str,
    patient_name: str,
    doctor_name: str,
    public_link: str,
    is_dynamic: bool = False,
    first_appointment_link: Optional[str] = None,
):
    subject = build_questionnaire_invite_email_subject(
        doctor_name, 
        has_first_appointment=bool(first_appointment_link)
    )
    
    html = build_questionnaire_invite_email_html(
        patient_name=patient_name,
        doctor_name=doctor_name,
        public_link=public_link,
        is_dynamic=is_dynamic,
        first_appointment_link=first_appointment_link,
    )
    return send_simple_html_email_ses(to_email, subject, html)