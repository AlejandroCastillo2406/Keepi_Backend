"""
Notificaciones unificadas: persistir en `notifications`, enviar FCM y (opcional) correo SES.

Uso típico desde cualquier ruta o servicio con `db: Session`:

    from app.services.notificaciones.user_notify import (
        notify_user_push_and_db,
        notify_user_push_db_and_email,
    )

    notify_user_push_and_db(
        db,
        user_id,
        title="Título",
        message="Cuerpo para in-app y push",
        payload={"foo": "bar"},
        push_data={"type": "custom", ...},  # strings para FCM data
    )

    notify_user_push_db_and_email(
        db,
        user_id,
        title="...",
        message="...",
        to_email="user@mail.com",
        email_subject="Asunto del correo",
        email_html="<p>...</p>",  # o None para generar HTML mínimo desde `message`
    )
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape as html_escape
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.notification import Notification
from app.services.notificaciones.fcm_push_service import send_push_to_user
from app.services.notificaciones.payment_email_service import (
    PaymentEmailResult,
    send_simple_html_email_ses,
)


def _as_uuid(value: UUID | str) -> UUID:
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


@dataclass
class NotifyUserResult:
    """Resultado de `notify_user_push_and_db`."""

    notification_id: str
    push_devices_ok: int


@dataclass
class NotifyUserWithEmailResult(NotifyUserResult):
    """Resultado de `notify_user_push_db_and_email`."""

    email: PaymentEmailResult


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
    """
    Crea fila en `notifications` (visible en GET de notificaciones), envía push FCM al usuario.

    Parámetros:
        db: sesión SQLAlchemy.
        user_id: UUID del usuario destino.
        title: título (in-app y push).
        message: texto largo; en push va como cuerpo del notification.
        notification_type: ej. \"info\", \"warning\", \"expiry\".
        payload: JSON extra para la app (prescription_id, etc.).
        document_id: opcional, FK a documents.
        push_data: pares clave-valor **string** para FCM `data` (se añade `notification_id`).

    Retorna:
        NotifyUserResult con id de la notificación y dispositivos a los que FCM entregó.
    """
    uid = _as_uuid(user_id)
    doc_uuid = _as_uuid(document_id) if document_id is not None else None
    body_text = (message or "").strip() or title

    row = Notification(
        user_id=uid,
        document_id=doc_uuid,
        title=title,
        message=body_text,
        type=notification_type,
        payload=dict(payload or {}),
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    merged: dict[str, str] = {k: str(v) for k, v in (push_data or {}).items()}
    merged.setdefault("notification_id", str(row.id))

    n_ok = send_push_to_user(
        db=db,
        user_id=str(uid),
        title=title,
        body=body_text,
        data=merged,
    )
    return NotifyUserResult(notification_id=str(row.id), push_devices_ok=n_ok)


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
    """
    Igual que `notify_user_push_and_db` y además envía correo por Amazon SES (HTML).

    Parámetros extra:
        to_email: destinatario (no se consulta el usuario en BD; pásalo explícito).
        email_subject: si es None, se usa `title`.
        email_html: si es None, se genera un párrafo HTML escapando `message`.
    """
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
