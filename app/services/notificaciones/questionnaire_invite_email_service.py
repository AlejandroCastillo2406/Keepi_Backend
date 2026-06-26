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
    enable_clinical_intake: bool = False,
    intake_only: bool = False,
    collect_prior_documents: bool = False,
    has_questionnaire: bool = False,
    scheduling_link: str | None = None,
) -> str:
    doctor = _format_doctor_display(doctor_name)
    parts: list[str] = []
    if enable_clinical_intake:
        parts.append("ficha clínica")
    if has_questionnaire:
        parts.append("cuestionario médico")
    if collect_prior_documents:
        parts.append("subida de documentos previos")
    steps_label = ", ".join(parts) if parts else "información clínica"

    paragraphs = [
        f"{doctor} te invitó a completar {steps_label} antes de tu consulta.",
        f"En un solo enlace podrás realizar: {steps_label}.",
    ]
    paragraphs.append(
        "No necesitas crear cuenta: el enlace es personal y funciona en celular o computadora."
    )

    headline = "Completa tu información clínica"
    if enable_clinical_intake and not has_questionnaire and not collect_prior_documents:
        headline = "Completa tu ficha clínica"
    elif has_questionnaire and not enable_clinical_intake and not collect_prior_documents:
        headline = "Responde tu cuestionario médico"

    return build_clinical_action_email_html(
        patient_name=patient_name,
        doctor_name=doctor_name,
        headline=headline,
        body_paragraphs=paragraphs,
        cta_label="Abrir enlace",
        cta_href=public_link,
        footer_note="Si el enlace expiró, solicita uno nuevo a tu médico.",
        badge_subtitle="Keepi · Solicitud de tu médico",
        scheduling_link=scheduling_link,
    )


def build_questionnaire_invite_email_subject(
    doctor_name: str,
    *,
    enable_clinical_intake: bool = False,
    has_questionnaire: bool = False,
) -> str:
    doctor = _format_doctor_display(doctor_name)
    if has_questionnaire and not enable_clinical_intake:
        return f"{_brand()} – {doctor} te envió un cuestionario"
    return f"{_brand()} – {doctor} te invitó a completar información clínica"


def send_questionnaire_invite_email(
    *,
    to_email: str,
    patient_name: str,
    doctor_name: str,
    public_link: str,
    enable_clinical_intake: bool = False,
    intake_only: bool = False,
    collect_prior_documents: bool = False,
    has_questionnaire: bool = False,
    scheduling_link: str | None = None,
):
    subject = build_questionnaire_invite_email_subject(
        doctor_name,
        enable_clinical_intake=enable_clinical_intake,
        has_questionnaire=has_questionnaire,
    )
    html = build_questionnaire_invite_email_html(
        patient_name=patient_name,
        doctor_name=doctor_name,
        public_link=public_link,
        enable_clinical_intake=enable_clinical_intake,
        intake_only=intake_only,
        collect_prior_documents=collect_prior_documents,
        has_questionnaire=has_questionnaire,
        scheduling_link=scheduling_link,
    )
    return send_simple_html_email_ses(to_email, subject, html)
