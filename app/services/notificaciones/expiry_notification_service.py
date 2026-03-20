from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, List

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.notification import Notification
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


def dispatch_expiry_emails(
    db: Session,
    *,
    send_date: date,
    days_before: int = 3,
) -> ExpiryEmailDispatchResult:
    #  si el documento vence el día (send_date + days_before),enviamos el recordatios en send_date PARA MIS PRUEBAS SOLO, ES OPCINAL EL CAMPO
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

    sent = 0
    errors = 0
    error_details: List[str] = []

    from app.services.notificaciones.payment_email_service import send_vencimiento_email_ses

    spanish_months = [
        "Enero",
        "Febrero",
        "Marzo",
        "Abril",
        "Mayo",
        "Junio",
        "Julio",
        "Agosto",
        "Septiembre",
        "Octubre",
        "Noviembre",
        "Diciembre",
    ]

    def _format_spanish_date(d: date) -> str:
        return f"{d.day} de {spanish_months[d.month - 1]}"

    def _format_days(days: int) -> str:
        if days == 1:
            return "1 día"
        return f"{days} días"


    already_notified = 0

    for row in candidate_rows:
        document_title = row.document_file_name or row.document_name
        if not document_title:
            continue

        # deduplicación
        stmt = pg_insert(NotificationsLog).values(
            user_id=row.user_id,
            document_id=row.document_id,
            target_date=send_date,
            days_before=days_before,
            ses_message_id=None,
        )
        stmt = stmt.on_conflict_do_nothing(
            index_elements=["user_id", "document_id", "target_date"]
        )
        insert_result = db.execute(stmt)
        inserted = int(getattr(insert_result, "rowcount", 0) or 0) > 0
        if not inserted:
            already_notified += 1
            continue
        db.commit()

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
            db.query(NotificationsLog).filter(
                NotificationsLog.user_id == row.user_id,
                NotificationsLog.document_id == row.document_id,
                NotificationsLog.target_date == send_date,
            ).delete(synchronize_session=False)
            db.commit()
            continue

        db.query(NotificationsLog).filter(
            NotificationsLog.user_id == row.user_id,
            NotificationsLog.document_id == row.document_id,
            NotificationsLog.target_date == send_date,
        ).update(
            {"ses_message_id": email_result.ses_message_id},
            synchronize_session=False,
        )
        db.commit()

        days_text = _format_days(days_before)

        notification = Notification(
            user_id=row.user_id,
            document_id=row.document_id,
            title=f"Vence en {days_text}",
            type="expiry",
            target_date=send_date,
        )
        db.add(notification)
        db.commit()

        sent += 1


    return ExpiryEmailDispatchResult(
        send_date=send_date,
        expiry_date=expiry_date,
        candidates_found=candidates_found,
        already_notified=already_notified,
        sent=sent,
        errors=errors,
        error_details=error_details,
    )

