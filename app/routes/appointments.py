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
from app.services.medical.appointment_service import AppointmentService

router = APIRouter()


@router.post("/doctor", response_model=AppointmentResponse)
async def create_appointment(
    body: AppointmentCreateRequest,
    current_user: User = Depends(require_doctor_user),
    db: Session = Depends(get_db),
):
    return AppointmentService.create_doctor_appointment(db, current_user.id, body)


@router.get("/doctor/calendar", response_model=list[AppointmentResponse])
async def get_doctor_calendar(
    start_at: datetime = Query(...),
    end_at: datetime = Query(...),
    current_user: User = Depends(require_doctor_user),
    db: Session = Depends(get_db),
):
    return AppointmentService.list_doctor_calendar(
        db, current_user.id, start_at, end_at
    )


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
