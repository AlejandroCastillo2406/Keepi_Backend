from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Iterable, List

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.notifications_log import NotificationsLog
from app.models.user import User


@dataclass(frozen=True)
class ExpiryEmailDispatchResult:
    send_date: date
    expiry_date: date
    candidates_found: int
    already_notified: int
    sent: int
    errors: int
    error_details: List[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "send_date": self.send_date.isoformat(),
            "expiry_date": self.expiry_date.isoformat(),
            "candidates_found": self.candidates_found,
            "already_notified": self.already_notified,
            "sent": self.sent,
            "errors": self.errors,
            "error_details": self.error_details,
        }


def _chunked(values: List[Any], chunk_size: int) -> Iterable[List[Any]]:
    for i in range(0, len(values), chunk_size):
        yield values[i : i + chunk_size]


def dispatch_expiry_emails(
    db: Session,
    *,
    send_date: date,
    days_before: int = 3,
) -> ExpiryEmailDispatchResult:
    # Regla calendario (UTC): si el documento vence el día (send_date + days_before),
    # entonces enviamos el recordatorio el día send_date.
    expiry_date = send_date + timedelta(days=days_before)

    candidate_rows = (
        db.query(
            Document.id.label("document_id"),
            Document.file_name.label("document_file_name"),
            Document.name.label("document_name"),
            User.id.label("user_id"),
            User.email.label("email"),
            User.name.label("user_name"),
        )
        .join(User, User.id == Document.user_id)
        .filter(Document.is_archived.is_(False))
        .filter(Document.expiry_date.isnot(None))
        .filter(User.is_active.is_(True))
        .filter(func.date(func.timezone("UTC", Document.expiry_date)) == expiry_date)
        .all()
    )

    candidates_found = len(candidate_rows)
    if candidates_found == 0:
        return ExpiryEmailDispatchResult(
            send_date=send_date,
            expiry_date=expiry_date,
            candidates_found=0,
            already_notified=0,
            sent=0,
            errors=0,
            error_details=[],
        )

    document_ids = [row.document_id for row in candidate_rows]
    existing_doc_ids: set[Any] = set()

    for batch in _chunked(document_ids, 500):
        rows = (
            db.query(NotificationsLog.document_id)
            .filter(NotificationsLog.notification_type == "expiry")
            .filter(NotificationsLog.target_date == send_date)
            .filter(NotificationsLog.document_id.in_(batch))
            .all()
        )
        existing_doc_ids.update(row[0] for row in rows)

    already_notified = len(existing_doc_ids)

    sent = 0
    errors = 0
    error_details: List[str] = []

    # Import aquí para evitar acoplar importaciones en el arranque.
    from app.services.notificaciones.payment_email_service import send_vencimiento_email_ses

    for row in candidate_rows:
        if row.document_id in existing_doc_ids:
            continue

        document_title = row.document_file_name or row.document_name
        if not document_title:
            continue

        email_result = send_vencimiento_email_ses(
            to_email=row.email,
            user_name=row.user_name,
            document_title=document_title,
            expiry_date=expiry_date,
            days_before=days_before,
        )

        if not email_result.success:
            errors += 1
            error_details.append(
                f"document_id={row.document_id} email_error={email_result.error or 'unknown'}"
            )
            continue

        stmt = pg_insert(NotificationsLog).values(
            user_id=row.user_id,
            document_id=row.document_id,
            notification_type="expiry",
            target_date=send_date,
            days_before=days_before,
            email_to=row.email,
            ses_message_id=email_result.ses_message_id,
        )
        stmt = stmt.on_conflict_do_nothing(
            index_elements=["user_id", "document_id", "notification_type", "target_date"]
        )
        db.execute(stmt)

        sent += 1

    db.commit()

    # Nota: `sent` cuenta intentos con envio exitoso; si hubo carrera entre dos ejecuciones,
    # el segundo insert podría ser ignorado por la deduplicación.
    return ExpiryEmailDispatchResult(
        send_date=send_date,
        expiry_date=expiry_date,
        candidates_found=candidates_found,
        already_notified=already_notified,
        sent=sent,
        errors=errors,
        error_details=error_details,
    )

