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
    intake_only: bool = False,
    collect_prior_documents: bool = False,
) -> str:
    doctor = _format_doctor_display(doctor_name)
    if intake_only:
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
        headline = "Completa tu ficha clínica"
        badge = "Ficha clínica · Keepi"
        cta = "Completar mi ficha"
    elif enable_clinical_intake:
        steps = ["ficha clínica (datos y antecedentes)"]
        if collect_prior_documents:
            steps.append("documentos médicos previos (opcional)")
        steps.append("cuestionario de salud")
        if len(steps) == 1:
            steps_text = steps[0]
        else:
            steps_text = ", ".join(steps[:-1]) + f" y {steps[-1]}"
        paragraphs = [
            f"{doctor} te invitó a completar tu información clínica antes de la consulta.",
            f"En un solo enlace, sin crear cuenta, completarás: {steps_text}.",
        ]
        if is_dynamic:
            paragraphs.append(
                "El cuestionario incluye preguntas adaptadas con IA según tus respuestas (máximo 10)."
            )
        paragraphs.append(
            "Todo ocurre en la misma página; no recibirás enlaces separados."
        )
        headline = "Completa tu información para la consulta"
        badge = "Formulario clínico · Keepi"
        cta = "Completar todo en un solo enlace"
    elif is_dynamic:
        paragraphs = [
            f"{doctor} te invitó a un cuestionario de salud personalizado con IA. "
            "Cada pregunta se adapta a tus respuestas anteriores (máximo 10 preguntas).",
        ]
        headline = "Cuestionario dinámico de salud"
        badge = "Cuestionario con IA"
        cta = "Completar cuestionario"
    else:
        paragraphs = [
            f"{doctor} te invitó a completar un cuestionario de salud. "
            "Tus respuestas ayudan a preparar mejor tu atención médica.",
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
    doctor_name: str,
    *,
    enable_clinical_intake: bool = True,
    intake_only: bool = False,
) -> str:
    doctor = _format_doctor_display(doctor_name)
    if intake_only:
        return f"{_brand()} – {doctor} te invitó a completar tu ficha clínica"
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
    intake_only: bool = False,
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
        is_dynamic=is_dynamic,
        enable_clinical_intake=enable_clinical_intake,
        intake_only=intake_only,
        collect_prior_documents=collect_prior_documents,
    )
    return send_simple_html_email_ses(to_email, subject, html)
