from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.appointment import Appointment
from app.models.doctor_procedure_block import DoctorProcedureBlock
from app.repositories.appointment_repository import AppointmentRepository
from app.repositories.procedure_block_repository import ProcedureBlockRepository

SCHEDULED_STATUSES = ("scheduled", "confirmed")
PENDING_STATUSES = (
    "pending_doctor_proposal",
    "pending_patient_approval",
    "pending_doctor_approval",
)


class IcalExportService:
    @staticmethod
    def build_doctor_calendar(
        db: Session,
        doctor_id: UUID,
        start_at: datetime,
        end_at: datetime,
        *,
        include_scheduled: bool = True,
        include_pending: bool = False,
        include_procedures: bool = True,
    ) -> str:
        events: list[str] = []

        if include_scheduled or include_pending:
            rows = AppointmentRepository(db).list_doctor_calendar(
                doctor_id, start_at, end_at
            )
            for row in rows:
                if row.status == "canceled":
                    continue
                if row.appointment_date is None:
                    continue
                if not _overlaps_range(row, start_at, end_at):
                    continue

                if row.status in SCHEDULED_STATUSES:
                    if not include_scheduled:
                        continue
                elif row.status in PENDING_STATUSES:
                    if not include_pending:
                        continue
                else:
                    continue

                events.append(_appointment_event(row))

        if include_procedures:
            blocks = ProcedureBlockRepository(db).list_in_range(
                doctor_id, start_at, end_at
            )
            for block in blocks:
                events.append(_procedure_event(block))

        body = "\r\n".join(events)
        header = "\r\n".join(
            [
                "BEGIN:VCALENDAR",
                "VERSION:2.0",
                "PRODID:-//Keepi//Agenda Doctor//ES",
                "CALSCALE:GREGORIAN",
                "METHOD:PUBLISH",
            ]
        )
        footer = "END:VCALENDAR"
        if body:
            return f"{header}\r\n{body}\r\n{footer}\r\n"
        return f"{header}\r\n{footer}\r\n"


def _overlaps_range(
    row: Appointment, start_at: datetime, end_at: datetime
) -> bool:
    start = row.appointment_date
    end = row.end_date or row.appointment_date
    if start is None or end is None:
        return False
    return start < end_at and end > start_at


def _appointment_event(row: Appointment) -> str:
    start = row.appointment_date
    end = row.end_date or row.appointment_date
    if start is None or end is None:
        return ""

    patient = getattr(row, "patient", None)
    patient_name = "Paciente"
    if patient is not None:
        patient_name = (patient.name or "").strip() or patient_name

    reason = (row.reason or "").strip() or "Consulta médica"
    summary = f"Cita — {patient_name}"
    description_parts = [f"Paciente: {patient_name}", f"Motivo: {reason}"]
    if row.status in PENDING_STATUSES:
        description_parts.append(f"Estado: {_status_label(row.status)}")

    uid = f"keepi-appt-{row.id}@keepi"
    return _vevent(
        uid=uid,
        start_at=start,
        end_at=end,
        summary=summary,
        description="\n".join(description_parts),
    )


def _procedure_event(row: DoctorProcedureBlock) -> str:
    title = (row.title or "").strip() or "Procedimiento"
    uid = f"keepi-proc-{row.id}@keepi"
    return _vevent(
        uid=uid,
        start_at=row.start_at,
        end_at=row.end_at,
        summary=f"Procedimiento — {title}",
        description=title,
    )


def _status_label(status: str) -> str:
    labels = {
        "pending_doctor_proposal": "Pendiente de propuesta",
        "pending_patient_approval": "Pendiente del paciente",
        "pending_doctor_approval": "Pendiente de aprobación",
    }
    return labels.get(status, status)


def _vevent(
    *,
    uid: str,
    start_at: datetime,
    end_at: datetime,
    summary: str,
    description: str,
) -> str:
    now = datetime.now(timezone.utc)
    lines = [
        "BEGIN:VEVENT",
        f"UID:{_escape(uid)}",
        f"DTSTAMP:{_format_utc(now)}",
        f"DTSTART:{_format_utc(start_at)}",
        f"DTEND:{_format_utc(end_at)}",
        f"SUMMARY:{_escape(summary)}",
        f"DESCRIPTION:{_escape(description)}",
        "END:VEVENT",
    ]
    return "\r\n".join(_fold_line(line) for line in lines)


def _format_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.strftime("%Y%m%dT%H%M%SZ")


def _escape(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def _fold_line(line: str) -> str:
    if len(line) <= 75:
        return line
    parts: list[str] = [line[:75]]
    rest = line[75:]
    while rest:
        parts.append(" " + rest[:74])
        rest = rest[74:]
    return "\r\n".join(parts)
