from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.roles import ROLE_DOCTOR
from app.core.security import require_no_temp_password_user
from app.models.doctor_scheduling import (
    AvailabilityRulesUpdateRequest,
    AvailabilityRuleResponse,
    PublicAvailabilityResponse,
    PublicBookAppointmentRequest,
    PublicBookAppointmentResponse,
    PublicSchedulingMetaResponse,
    SchedulingSettingsResponse,
    SchedulingSettingsUpdateRequest,
)
from app.models.user import User
from app.services.medical.doctor_availability_service import DoctorAvailabilityService

router = APIRouter()


@router.get("/settings", response_model=SchedulingSettingsResponse)
async def get_scheduling_settings(
    current_user: User = Depends(require_no_temp_password_user),
    db: Session = Depends(get_db),
):
    if current_user.role is None or current_user.role.name != ROLE_DOCTOR:
        raise HTTPException(status_code=403, detail="Solo usuarios con rol DOCTOR.")
    return DoctorAvailabilityService.get_settings(db, current_user.id)


@router.put("/settings", response_model=SchedulingSettingsResponse)
async def update_scheduling_settings(
    body: SchedulingSettingsUpdateRequest,
    current_user: User = Depends(require_no_temp_password_user),
    db: Session = Depends(get_db),
):
    if current_user.role is None or current_user.role.name != ROLE_DOCTOR:
        raise HTTPException(status_code=403, detail="Solo usuarios con rol DOCTOR.")
    return DoctorAvailabilityService.update_settings(
        db,
        current_user.id,
        body.slot_duration_minutes,
        body.timezone,
    )


@router.get("/availability-rules", response_model=list[AvailabilityRuleResponse])
async def get_availability_rules(
    current_user: User = Depends(require_no_temp_password_user),
    db: Session = Depends(get_db),
):
    if current_user.role is None or current_user.role.name != ROLE_DOCTOR:
        raise HTTPException(status_code=403, detail="Solo usuarios con rol DOCTOR.")
    return DoctorAvailabilityService.list_rules(db, current_user.id)


@router.put("/availability-rules", response_model=list[AvailabilityRuleResponse])
async def replace_availability_rules(
    body: AvailabilityRulesUpdateRequest,
    current_user: User = Depends(require_no_temp_password_user),
    db: Session = Depends(get_db),
):
    if current_user.role is None or current_user.role.name != ROLE_DOCTOR:
        raise HTTPException(status_code=403, detail="Solo usuarios con rol DOCTOR.")
    return DoctorAvailabilityService.replace_rules(db, current_user.id, body.rules)


@router.get("/available-slots", response_model=PublicAvailabilityResponse)
async def get_doctor_available_slots(
    from_date: date = Query(..., alias="from"),
    to_date: date = Query(..., alias="to"),
    current_user: User = Depends(require_no_temp_password_user),
    db: Session = Depends(get_db),
):
    if current_user.role is None or current_user.role.name != ROLE_DOCTOR:
        raise HTTPException(status_code=403, detail="Solo usuarios con rol DOCTOR.")
    slots, message = DoctorAvailabilityService.compute_available_slots(
        db, current_user.id, from_date, to_date
    )
    return PublicAvailabilityResponse(slots=slots, message=message)


public_router = APIRouter()


@public_router.get("/{token}", response_model=PublicSchedulingMetaResponse)
async def get_public_scheduling_meta(
    token: str,
    db: Session = Depends(get_db),
):
    return DoctorAvailabilityService.get_public_meta(db, token)


@public_router.get("/{token}/availability", response_model=PublicAvailabilityResponse)
async def get_public_availability(
    token: str,
    from_date: date = Query(..., alias="from"),
    to_date: date = Query(..., alias="to"),
    db: Session = Depends(get_db),
):
    return DoctorAvailabilityService.get_public_availability(
        db, token, from_date, to_date
    )


@public_router.post("/{token}/book", response_model=PublicBookAppointmentResponse)
async def book_public_appointment(
    token: str,
    body: PublicBookAppointmentRequest,
    db: Session = Depends(get_db),
):
    return DoctorAvailabilityService.book_public_slot(db, token, body)
