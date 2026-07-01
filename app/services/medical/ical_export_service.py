from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models.appointment import Appointment
from app.models.doctor_procedure_block import DoctorProcedureBlock
from app.repositories.appointment_repository import AppointmentRepository
from app.repositories.procedure_block_repository import ProcedureBlockRepository
from app.services.medical.doctor_availability_service import DoctorAvailabilityService

SCHEDULED_STATUSES = ("scheduled", "confirmed")
PENDING_STATUSES = (
    "pending_doctor_proposal",
    "pending_patient_approval",
    "pending_doctor_approval",
)
DEFAULT_TIMEZONE = "America/Mexico_City"


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
        timezone_name: str | None = None,
        appointment_ids: set[UUID] | None = None,
        procedure_ids: set[UUID] | None = None,
    ) -> str:
        tz_name = _resolve_timezone(db, doctor_id, timezone_name)
        events: list[str] = []
        selective = appointment_ids is not None or procedure_ids is not None
        appt_ids = appointment_ids or set()
        proc_ids = procedure_ids or set()

        if selective or include_scheduled or include_pending:
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

                if selective:
                    if row.id not in appt_ids:
                        continue
                elif row.status in SCHEDULED_STATUSES:
                    if not include_scheduled:
                        continue
                elif row.status in PENDING_STATUSES:
                    if not include_pending:
                        continue
                else:
                    continue

                events.append(_appointment_event(row, tz_name))

        if selective or include_procedures:
            blocks = ProcedureBlockRepository(db).list_in_range(
                doctor_id, start_at, end_at
            )
            for block in blocks:
                if selective and block.id not in proc_ids:
                    continue
                events.append(_procedure_event(block, tz_name))

        header_lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Keepi//Agenda Doctor//ES",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
            f"X-WR-TIMEZONE:{tz_name}",
        ]
        header = "\r\n".join(line for line in header_lines if line)
        footer = "END:VCALENDAR"
        body = "\r\n".join(events)
        if body:
            return f"{header}\r\n{body}\r\n{footer}\r\n"
        return f"{header}\r\n{footer}\r\n"


def _resolve_timezone(
    db: Session, doctor_id: UUID, timezone_name: str | None
) -> str:
    if timezone_name and timezone_name.strip():
        return timezone_name.strip()
    try:
        return DoctorAvailabilityService.get_settings(db, doctor_id).timezone
    except Exception:
        return DEFAULT_TIMEZONE


def _safe_tz(tz_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return ZoneInfo(DEFAULT_TIMEZONE)


def _overlaps_range(
    row: Appointment, start_at: datetime, end_at: datetime
) -> bool:
    start = row.appointment_date
    end = row.end_date or row.appointment_date
    if start is None or end is None:
        return False
    return start < end_at and end > start_at


def _appointment_event(row: Appointment, tz_name: str) -> str:
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
        tz_name=tz_name,
    )


def _procedure_event(row: DoctorProcedureBlock, tz_name: str) -> str:
    title = (row.title or "").strip() or "Procedimiento"
    uid = f"keepi-proc-{row.id}@keepi"
    return _vevent(
        uid=uid,
        start_at=row.start_at,
        end_at=row.end_at,
        summary=f"Procedimiento — {title}",
        description=title,
        tz_name=tz_name,
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
    tz_name: str,
) -> str:
    now = datetime.now(timezone.utc)
    lines = [
        "BEGIN:VEVENT",
        f"UID:{_escape(uid)}",
        f"DTSTAMP:{_format_utc(now)}",
        f"DTSTART:{_format_local(start_at, tz_name)}",
        f"DTEND:{_format_local(end_at, tz_name)}",
        f"SUMMARY:{_escape(summary)}",
        f"DESCRIPTION:{_escape(description)}",
        "END:VEVENT",
    ]
    return "\r\n".join(_fold_line(line) for line in lines)


def _format_local(value: datetime, tz_name: str) -> str:
    local = value.astimezone(_safe_tz(tz_name))
    return local.strftime("%Y%m%dT%H%M%S")


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
