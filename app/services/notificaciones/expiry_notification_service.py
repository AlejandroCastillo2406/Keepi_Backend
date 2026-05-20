from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, List

from sqlalchemy.orm import Session

from app.repositories.expiry_candidate_repository import ExpiryCandidateRepository
from app.repositories.notifications_log_repository import NotificationsLogRepository

logger = logging.getLogger(__name__)

# Días calendario antes del vencimiento en los que se notifica (solo fecha, no hora).
EXPIRY_REMINDER_DAYS_BEFORE: tuple[int, ...] = (30, 15, 3)

_SPANISH_MONTHS = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)


@dataclass(frozen=True)
class ExpiryReminderDispatchResult:
    send_date: date
    expiry_date: date
    days_before: int
    candidates_found: int
    already_notified: int
    sent: int
    push_devices_ok: int
    errors: int
    error_details: List[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "send_date": self.send_date.isoformat(),
            "expiry_date": self.expiry_date.isoformat(),
            "days_before": self.days_before,
            "candidates_found": self.candidates_found,
            "already_notified": self.already_notified,
            "sent": self.sent,
            "push_devices_ok": self.push_devices_ok,
            "errors": self.errors,
            "error_details": self.error_details,
        }


def _format_spanish_date(d: date) -> str:
    return f"{d.day} de {_SPANISH_MONTHS[d.month - 1]}"


def _format_days(days: int) -> str:
    if days == 1:
        return "1 día"
    return f"{days} días"


def _document_title(row: Any) -> str:
    title = (row.document_file_name or row.document_name or "").strip()
    return title or "Documento"


def dispatch_expiry_reminders(
    db: Session,
    *,
    send_date: date,
    days_before: int,
) -> ExpiryReminderDispatchResult:
    """
    Busca documentos cuya fecha de vencimiento (solo día UTC) sea
    send_date + days_before y envía notificación in-app + push.
    """
    if days_before not in EXPIRY_REMINDER_DAYS_BEFORE:
        raise ValueError(
            f"days_before debe ser uno de {EXPIRY_REMINDER_DAYS_BEFORE}, recibido {days_before}"
        )

    expiry_date = send_date + timedelta(days=days_before)
    candidates = ExpiryCandidateRepository(db).list_candidates_for_expiry_date(
        expiry_date
    )
    candidates_found = len(candidates)
    if candidates_found == 0:
        return ExpiryReminderDispatchResult(
            send_date=send_date,
            expiry_date=expiry_date,
            days_before=days_before,
            candidates_found=0,
            already_notified=0,
            sent=0,
            push_devices_ok=0,
            errors=0,
            error_details=[],
        )

    log_repo = NotificationsLogRepository(db)
    from app.services.notificaciones.user_notify import notify_user_push_and_db

    sent = 0
    push_devices_ok = 0
    errors = 0
    error_details: List[str] = []
    already_notified = 0
    days_text = _format_days(days_before)
    expiry_label = _format_spanish_date(expiry_date)

    for row in candidates:
        doc_title = _document_title(row)

        inserted = log_repo.try_insert_expiry_row(
            user_id=row.user_id,
            document_id=row.document_id,
            send_date=send_date,
            days_before=days_before,
            email_to=(row.email or "").strip(),
        )
        if not inserted:
            already_notified += 1
            continue

        title = f"Vence en {days_text}"
        message = (
            f'"{doc_title}" vence el {expiry_label} '
            f"(faltan {days_text})."
        )
        payload = {
            "type": "document_expiring",
            "days_before": days_before,
            "expiry_date": expiry_date.isoformat(),
            "document_name": doc_title,
        }
        push_data = {
            "type": "document_expiring",
            "document_id": str(row.document_id),
            "days_before": str(days_before),
            "expiry_date": expiry_date.isoformat(),
            "title": title,
            "body": message,
        }

        try:
            result = notify_user_push_and_db(
                db,
                row.user_id,
                title=title,
                message=message,
                notification_type="expiry",
                payload=payload,
                document_id=str(row.document_id),
                push_data=push_data,
            )
            push_devices_ok += result.push_devices_ok
            sent += 1
            if result.push_devices_ok == 0:
                logger.warning(
                    "expiry reminder: in-app OK, push 0 devices user=%s doc=%s days_before=%s",
                    row.user_id,
                    row.document_id,
                    days_before,
                )
        except Exception as exc:
            errors += 1
            error_details.append(
                f"document_id={row.document_id} error={exc!s}"
            )
            log_repo.delete_expiry_row(
                user_id=row.user_id,
                document_id=row.document_id,
                send_date=send_date,
            )
            logger.exception(
                "Error enviando recordatorio de vencimiento doc=%s days_before=%s",
                row.document_id,
                days_before,
            )

    return ExpiryReminderDispatchResult(
        send_date=send_date,
        expiry_date=expiry_date,
        days_before=days_before,
        candidates_found=candidates_found,
        already_notified=already_notified,
        sent=sent,
        push_devices_ok=push_devices_ok,
        errors=errors,
        error_details=error_details,
    )


def dispatch_expiry_reminders_all_milestones(
    db: Session,
    *,
    send_date: date,
) -> dict[str, Any]:
    """Ejecuta 30, 15 y 3 días antes del vencimiento para la fecha de envío dada."""
    by_milestone: dict[str, Any] = {}
    totals = {
        "candidates_found": 0,
        "already_notified": 0,
        "sent": 0,
        "push_devices_ok": 0,
        "errors": 0,
        "error_details": [],
    }
    for days_before in EXPIRY_REMINDER_DAYS_BEFORE:
        result = dispatch_expiry_reminders(
            db, send_date=send_date, days_before=days_before
        )
        by_milestone[str(days_before)] = result.to_dict()
        totals["candidates_found"] += result.candidates_found
        totals["already_notified"] += result.already_notified
        totals["sent"] += result.sent
        totals["push_devices_ok"] += result.push_devices_ok
        totals["errors"] += result.errors
        totals["error_details"].extend(result.error_details)

    return {
        "send_date": send_date.isoformat(),
        "milestones_days_before": list(EXPIRY_REMINDER_DAYS_BEFORE),
        "milestones": by_milestone,
        **totals,
    }


# Compatibilidad con endpoint anterior (solo correo).
def dispatch_expiry_emails(
    db: Session,
    *,
    send_date: date,
    days_before: int = 3,
) -> ExpiryReminderDispatchResult:
    """Deprecado: usar dispatch_expiry_reminders (push + in-app)."""
    return dispatch_expiry_reminders(db, send_date=send_date, days_before=days_before)
