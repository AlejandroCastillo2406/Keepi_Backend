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
    enable_clinical_intake: bool = True,
    intake_only: bool = True,
    collect_prior_documents: bool = False,
) -> str:
    doctor = _format_doctor_display(doctor_name)
    paragraphs = [
        f"{doctor} te invitó a completar tu ficha clínica antes de la consulta.",
        "En un solo enlace podrás registrar datos personales, antecedentes familiares, "
        "alergias, medicamentos y motivo de consulta.",
    ]
    if collect_prior_documents:
        paragraphs.append(
            "También podrás subir estudios o informes médicos previos (opcional)."
        )
    paragraphs.append(
        "No necesitas crear cuenta: el enlace es personal y funciona en celular o computadora."
    )
    return build_clinical_action_email_html(
        patient_name=patient_name,
        doctor_name=doctor_name,
        headline="Completa tu ficha clínica",
        body_paragraphs=paragraphs,
        cta_label="Completar mi ficha",
        cta_href=public_link,
        footer_note="Si el enlace expiró, solicita uno nuevo a tu médico.",
        badge_subtitle="Ficha clínica · Keepi",
    )


def build_questionnaire_invite_email_subject(
    doctor_name: str,
    *,
    enable_clinical_intake: bool = True,
    intake_only: bool = True,
) -> str:
    doctor = _format_doctor_display(doctor_name)
    return f"{_brand()} – {doctor} te invitó a completar tu ficha clínica"


def send_questionnaire_invite_email(
    *,
    to_email: str,
    patient_name: str,
    doctor_name: str,
    public_link: str,
    enable_clinical_intake: bool = True,
    intake_only: bool = True,
    collect_prior_documents: bool = False,
):
    subject = build_questionnaire_invite_email_subject(
        doctor_name,
        enable_clinical_intake=enable_clinical_intake,
        intake_only=intake_only,
    )
    html = build_questionnaire_invite_email_html(
        patient_name=patient_name,
        doctor_name=doctor_name,
        public_link=public_link,
        enable_clinical_intake=enable_clinical_intake,
        intake_only=intake_only,
        collect_prior_documents=collect_prior_documents,
    )
    return send_simple_html_email_ses(to_email, subject, html)
