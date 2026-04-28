from __future__ import annotations

from html import escape as html_escape
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.dto.notify_user_result import NotifyUserResult, NotifyUserWithEmailResult
from app.services.notificaciones.fcm_push_service import send_push_to_user
from app.services.notificaciones.payment_email_service import send_simple_html_email_ses


def _as_uuid(value: UUID | str) -> UUID:
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


def notify_user_push_and_db(
    db: Session,
    user_id: UUID | str,
    *,
    title: str,
    message: str,
    notification_type: str = "info",
    payload: dict[str, Any] | None = None,
    document_id: UUID | str | None = None,
    push_data: dict[str, str] | None = None,
) -> NotifyUserResult:
    from app.services.notificaciones.notification_service import NotificationService

    return NotificationService(db).notify_user_push_in_app(
        user_id,
        title=title,
        message=message,
        notification_type=notification_type,
        payload=payload,
        document_id=document_id,
        push_data=push_data,
    )


def notify_user_push_db_and_email(
    db: Session,
    user_id: UUID | str,
    *,
    title: str,
    message: str,
    to_email: str,
    notification_type: str = "info",
    payload: dict[str, Any] | None = None,
    document_id: UUID | str | None = None,
    push_data: dict[str, str] | None = None,
    email_subject: str | None = None,
    email_html: str | None = None,
) -> NotifyUserWithEmailResult:
    base = notify_user_push_and_db(
        db,
        user_id,
        title=title,
        message=message,
        notification_type=notification_type,
        payload=payload,
        document_id=document_id,
        push_data=push_data,
    )
    subject = (email_subject or title).strip() or "Notificación"
    if email_html and email_html.strip():
        html = email_html
    else:
        html = f"<p>{html_escape((message or title).strip())}</p>"

    email_res = send_simple_html_email_ses(to_email.strip(), subject, html)
    return NotifyUserWithEmailResult(
        notification_id=base.notification_id,
        push_devices_ok=base.push_devices_ok,
        email=email_res,
    )
