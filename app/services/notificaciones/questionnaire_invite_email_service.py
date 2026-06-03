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


def build_questionnaire_invite_email_html(
    *,
    patient_name: str,
    doctor_name: str,
    public_link: str,
    is_dynamic: bool = False,
    enable_clinical_intake: bool = True,
) -> str:
    doctor = _format_doctor_display(doctor_name)
    if enable_clinical_intake:
        paragraphs = [
            f"{doctor} te invitó a completar tu información clínica antes de la consulta.",
            "En el mismo enlace podrás llenar tu ficha (datos, antecedentes, alergias, medicamentos) "
            "y después el cuestionario de salud.",
            "No necesitas crear cuenta: el enlace es personal y funciona en celular o computadora.",
        ]
        if is_dynamic:
            paragraphs.append(
                "El cuestionario incluye preguntas adaptadas con IA según tus respuestas (máximo 10)."
            )
        headline = "Completa tu información para la consulta"
        badge = "Alta clínica · Keepi"
        cta = "Completar mi información"
    elif is_dynamic:
        paragraphs = [
            f"{doctor} te invitó a un cuestionario de salud personalizado con IA. "
            "Cada pregunta se adapta a tus respuestas anteriores (máximo 10 preguntas).",
            "El enlace es personal y puedes contestarlo desde el celular o la computadora.",
        ]
        headline = "Cuestionario dinámico de salud"
        badge = "Cuestionario con IA"
        cta = "Completar cuestionario"
    else:
        paragraphs = [
            f"{doctor} te invitó a completar un cuestionario de salud. "
            "Tus respuestas ayudan a preparar mejor tu atención médica.",
            "El enlace es personal y puedes contestarlo desde el celular o la computadora.",
        ]
        headline = "Cuestionario de salud"
        badge = "Cuestionario de salud"
        cta = "Completar cuestionario"
    return build_clinical_action_email_html(
        patient_name=patient_name,
        doctor_name=doctor_name,
        headline=headline,
        body_paragraphs=paragraphs,
        cta_label=cta,
        cta_href=public_link,
        footer_note="Si el enlace expiró, solicita uno nuevo a tu médico.",
        badge_subtitle=badge,
    )


def build_questionnaire_invite_email_subject(
    doctor_name: str, *, enable_clinical_intake: bool = True
) -> str:
    doctor = _format_doctor_display(doctor_name)
    if enable_clinical_intake:
        return f"{_brand()} – {doctor} te invitó a completar tu información clínica"
    return f"{_brand()} – {doctor} te envió un cuestionario"


def send_questionnaire_invite_email(
    *,
    to_email: str,
    patient_name: str,
    doctor_name: str,
    public_link: str,
    is_dynamic: bool = False,
    enable_clinical_intake: bool = True,
):
    subject = build_questionnaire_invite_email_subject(
        doctor_name, enable_clinical_intake=enable_clinical_intake
    )
    html = build_questionnaire_invite_email_html(
        patient_name=patient_name,
        doctor_name=doctor_name,
        public_link=public_link,
        is_dynamic=is_dynamic,
        enable_clinical_intake=enable_clinical_intake,
    )
    return send_simple_html_email_ses(to_email, subject, html)
