from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.dto.analysis_request_dto import AnalysisRequestResponse
from app.dto.consultation_bootstrap_dto import ConsultationBootstrapResponse
from app.dto.consultation_context_dto import ConsultationStatsDto
from app.dto.timeline_dto import EventType, TimelineEventResponse
from app.models.appointment import Appointment
from app.repositories.analysis_request_repository import AnalysisRequestRepository
from app.repositories.appointment_repository import AppointmentRepository
from app.services.medical.appointment_service import AppointmentService
from app.services.medical.consultation_context_service import ConsultationContextService
from app.services.medical.doctor_timeline_note_service import DoctorTimelineNoteService
from app.services.medical.patient_timeline_service import PatientTimelineService

_MONTHS_ES = (
    "ENE",
    "FEB",
    "MAR",
    "ABR",
    "MAY",
    "JUN",
    "JUL",
    "AGO",
    "SEP",
    "OCT",
    "NOV",
    "DIC",
)


def _as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _fmt_date(dt: datetime) -> str:
    local = dt.astimezone(timezone.utc)
    return f"{local.day:02d} {_MONTHS_ES[local.month - 1]} {local.year}"


def _fmt_time(dt: datetime) -> str:
    local = dt.astimezone(timezone.utc)
    return f"{local.hour:02d}:{local.minute:02d}"


class ConsultationBootstrapService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def _stats_from(
        self,
        doctor_id: uuid.UUID,
        patient_id: uuid.UUID,
        requests: list,
        timeline_count: int,
    ) -> ConsultationStatsDto:
        uploaded = sum(
            1
            for r in requests
            if r.status == "completed" and r.document_id is not None
        )
        pending = sum(
            1 for r in requests if r.status == "pending" and r.document_id is None
        )
        attendance = AppointmentService.compute_attendance_stats(
            self._db, doctor_id, patient_id
        )
        return ConsultationStatsDto(
            analysis_requested=len(requests),
            analysis_uploaded=uploaded,
            analysis_pending=pending,
            timeline_events=timeline_count,
            **attendance,
        )

    @staticmethod
    def _find_timeline_event(
        timeline: List[TimelineEventResponse], event_id: str
    ) -> Optional[TimelineEventResponse]:
        for ev in timeline:
            if ev.id == event_id:
                return ev
        bare = event_id.replace("appt_", "").replace("anreq_", "").replace(
            "anupl_", ""
        ).replace("pres_", "")
        for ev in timeline:
            ev_bare = ev.id.replace("appt_", "").replace("anreq_", "").replace(
                "anupl_", ""
            ).replace("pres_", "")
            if ev_bare == bare and bare:
                return ev
        return None

    @staticmethod
    def _appointment_fallback(
        appointment: Appointment,
    ) -> TimelineEventResponse:
        when = _as_utc(appointment.appointment_date or appointment.created_at)
        reason = (appointment.reason or "").strip() or "Consulta"
        return TimelineEventResponse(
            id=f"appt_{appointment.id}",
            date=_fmt_date(when),
            time=_fmt_time(when),
            title="Cita médica",
            actor="Doctor",
            event_type=EventType.APPOINTMENT,
            subtitle=reason,
            description=reason,
            occurred_at=when.isoformat(),
            visual_state="completed",
        )

    def get_bootstrap(
        self,
        doctor_id: uuid.UUID,
        patient_id: uuid.UUID,
        appointment_id: uuid.UUID,
    ) -> ConsultationBootstrapResponse:
        timeline_svc = PatientTimelineService(self._db)
        timeline = timeline_svc.timeline_for_doctor_patient(doctor_id, patient_id)

        analysis_rows = AnalysisRequestRepository(self._db).get_all_by_patient(
            patient_id
        )
        analysis = [
            AnalysisRequestResponse.model_validate(row) for row in analysis_rows
        ]
        stats = self._stats_from(doctor_id, patient_id, analysis_rows, len(timeline))

        context = ConsultationContextService(self._db).get_context(
            doctor_id, patient_id, stats=stats
        )

        event_id = f"appt_{appointment_id}"
        appointment_event = self._find_timeline_event(timeline, event_id)
        if appointment_event is None:
            appt = AppointmentRepository(self._db).get_by_id(appointment_id)
            if appt is None or appt.patient_id != patient_id:
                raise HTTPException(status_code=404, detail="Cita no encontrada.")
            ConsultationContextService(self._db)._ensure_patient(doctor_id, patient_id)
            appointment_event = self._appointment_fallback(appt)

        doctor_note_content: Optional[str] = None
        note_svc = DoctorTimelineNoteService(self._db)
        try:
            note = note_svc.get_note_content(
                doctor_id=doctor_id,
                patient_id=patient_id,
                timeline_event_id=appointment_event.id,
            )
            doctor_note_content = note.content
        except HTTPException as exc:
            if exc.status_code != 404:
                raise

        return ConsultationBootstrapResponse(
            context=context,
            timeline=timeline,
            analysis_requests=analysis,
            appointment_event=appointment_event,
            doctor_note_content=doctor_note_content,
        )
