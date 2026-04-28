from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, List

from sqlalchemy.orm import Session

from app.models.notification import Notification
from app.repositories.expiry_candidate_repository import ExpiryCandidateRepository
from app.repositories.notification_repository import NotificationRepository
from app.repositories.notifications_log_repository import NotificationsLogRepository


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
    expiry_date = send_date + timedelta(days=days_before)
    candidates = ExpiryCandidateRepository(db).list_candidates_for_expiry_date(
        expiry_date
    )
    candidates_found = len(candidates)
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

    log_repo = NotificationsLogRepository(db)
    notif_repo = NotificationRepository(db)

    sent = 0
    errors = 0
    error_details: List[str] = []
    already_notified = 0

    from app.services.notificaciones.payment_email_service import (
        send_vencimiento_email_ses,
    )

    def _format_days(days: int) -> str:
        if days == 1:
            return "1 día"
        return f"{days} días"

    for row in candidates:
        document_title = row.document_file_name or row.document_name
        if not document_title:
            continue

        inserted = log_repo.try_insert_expiry_row(
            user_id=row.user_id,
            document_id=row.document_id,
            send_date=send_date,
            days_before=days_before,
            email_to=row.email,
        )
        if not inserted:
            already_notified += 1
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
            log_repo.delete_expiry_row(
                user_id=row.user_id,
                document_id=row.document_id,
                send_date=send_date,
            )
            continue

        log_repo.update_ses_message_id(
            user_id=row.user_id,
            document_id=row.document_id,
            send_date=send_date,
            ses_message_id=email_result.ses_message_id,
        )

        days_text = _format_days(days_before)
        notif_repo.add(
            Notification(
                user_id=row.user_id,
                document_id=row.document_id,
                title=f"Vence en {days_text}",
                message=f"Tu documento vence en {days_text}.",
                type="expiry",
                target_date=send_date,
                payload={
                    "days_before": days_before,
                    "expiry_date": expiry_date.isoformat(),
                },
                read=False,
                read_at=None,
            )
        )
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
