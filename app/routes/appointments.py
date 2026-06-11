from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_doctor_user, require_patient_user
from app.models.appointment import (
    AppointmentCreateRequest,
    AppointmentDoctorProposeRequest,
    AppointmentResponse,
)
from app.models.user import User
from app.dto.timeline_dto import EventType
from app.services.medical.appointment_service import AppointmentService
from app.services.medical.doctor_timeline_note_service import DoctorTimelineNoteService

router = APIRouter()


@router.post("/doctor", response_model=AppointmentResponse)
async def create_appointment(
    body: AppointmentCreateRequest,
    current_user: User = Depends(require_doctor_user),
    db: Session = Depends(get_db),
):
    appt = AppointmentService.create_doctor_appointment(db, current_user.id, body)
    if body.notes and body.notes.strip():
        DoctorTimelineNoteService(db).save_note_for_event(
            doctor_id=current_user.id,
            patient_id=appt.patient_id,
            timeline_event_id=f"appt_{appt.id}",
            event_type=EventType.APPOINTMENT.value,
            content=body.notes.strip(),
        )
    return appt


@router.get("/doctor/calendar", response_model=list[AppointmentResponse])
async def get_doctor_calendar(
    start_at: datetime = Query(...),
    end_at: datetime = Query(...),
    current_user: User = Depends(require_doctor_user),
    db: Session = Depends(get_db),
):
    rows = AppointmentService.list_doctor_calendar(
        db, current_user.id, start_at, end_at
    )
    return [AppointmentResponse.from_entity(r) for r in rows]


@router.get("/mine", response_model=list[AppointmentResponse])
async def get_patient_appointments(
    current_user: User = Depends(require_patient_user),
    db: Session = Depends(get_db),
):
    return AppointmentService.list_patient_appointments(db, current_user.id)


@router.get("/{appointment_id}", response_model=AppointmentResponse)
async def get_appointment_detail(
    appointment_id: UUID,
    current_user: User = Depends(require_patient_user),
    db: Session = Depends(get_db),
):
    return AppointmentService.get_appointment_for_patient(
        db, appointment_id, current_user.id
    )


@router.post("/{appointment_id}/doctor/propose", response_model=AppointmentResponse)
async def doctor_propose_time(
    appointment_id: UUID,
    body: AppointmentDoctorProposeRequest,
    current_user: User = Depends(require_doctor_user),
    db: Session = Depends(get_db),
):
    return AppointmentService.doctor_propose_and_notify(
        db,
        appointment_id,
        current_user.id,
        body,
        current_user.name or "",
    )


@router.post("/{appointment_id}/cancel", response_model=AppointmentResponse)
async def cancel_doctor_appointment(
    appointment_id: UUID,
    current_user: User = Depends(require_doctor_user),
    db: Session = Depends(get_db),
):
    return AppointmentService.cancel_doctor_appointment(
        db, appointment_id, current_user.id
    )


@router.post("/{appointment_id}/doctor/approve", response_model=AppointmentResponse)
async def doctor_approve_appointment(
    appointment_id: UUID,
    current_user: User = Depends(require_doctor_user),
    db: Session = Depends(get_db),
):
    return AppointmentService.approve_doctor_approval(
        db,
        appointment_id,
        current_user.id,
        current_user.name or "",
    )


@router.post("/{appointment_id}/doctor/reject", response_model=AppointmentResponse)
async def doctor_reject_appointment(
    appointment_id: UUID,
    current_user: User = Depends(require_doctor_user),
    db: Session = Depends(get_db),
):
    return AppointmentService.reject_doctor_approval(
        db,
        appointment_id,
        current_user.id,
        current_user.name or "",
    )