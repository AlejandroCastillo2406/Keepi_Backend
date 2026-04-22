"""Notificación al paciente para completar cuestionario diagnóstico."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.user import User
from app.services.notificaciones.user_notify import notify_user_push_and_db


def notify_diagnostic_questionnaire_required(
    db: Session,
    *,
    patient_id,
    doctor: User,
) -> None:
    name = (doctor.name or "Tu médico").strip()
    notify_user_push_and_db(
        db,
        patient_id,
        title="Cuestionario diagnóstico",
        message=(
            f"El Dr. {name} solicita la realización de un cuestionario diagnóstico; "
            "debes completarlo lo antes posible."
        ),
        notification_type="diagnostic_questionnaire_required",
        payload={
            "action": "open_diagnostic_questionnaire",
            "doctor_id": str(doctor.id),
            "doctor_name": name,
        },
        push_data={
            "type": "diagnostic_questionnaire_required",
            "action": "open_diagnostic_questionnaire",
            "doctor_name": name,
        },
    )
