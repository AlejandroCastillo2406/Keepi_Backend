from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import (
    require_doctor_user,
    require_no_temp_password_user,
    require_patient_user,
)
from app.models.appointment import (
    AppointmentAttendanceRequest,
    AppointmentCreateRequest,
    AppointmentDoctorProposeRequest,
    AppointmentDoctorRescheduleRequest,
    AppointmentResponse,
    DoctorCalendarResponse,
    PublicAppointmentMetaResponse,
    PublicAppointmentRespondRequest,
    PublicAppointmentRespondResponse,
)
from app.models.doctor_procedure_block import (
    ProcedureBlockCreateRequest,
    ProcedureBlockResponse,
)
from app.models.user import User
from app.dto.timeline_dto import EventType
from app.services.medical.appointment_service import AppointmentService
from app.services.medical.doctor_availability_service import DoctorAvailabilityService
from app.services.medical.doctor_timeline_note_service import DoctorTimelineNoteService
from app.services.medical.ical_export_service import IcalExportService
from app.services.medical.procedure_block_service import ProcedureBlockService

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
    AppointmentService.notify_patient_doctor_scheduled(
        db,
        appt,
        doctor_name=current_user.name or "",
    )
    return appt


@router.get("/doctor/calendar", response_model=DoctorCalendarResponse)
async def get_doctor_calendar(
    start_at: datetime = Query(...),
    end_at: datetime = Query(...),
    current_user: User = Depends(require_doctor_user),
    db: Session = Depends(get_db),
):
    rows = AppointmentService.list_doctor_calendar(
        db, current_user.id, start_at, end_at
    )
    procedures = ProcedureBlockService.list_for_calendar(
        db, current_user.id, start_at, end_at
    )
    return DoctorCalendarResponse(
        appointments=[AppointmentResponse.from_entity(r) for r in rows],
        procedures=procedures,
        consultation_schedule=DoctorAvailabilityService.get_consultation_schedule(
            db, current_user.id
        ),
    )


@router.get("/doctor/export.ics")
async def export_doctor_calendar_ics(
    start_at: datetime = Query(...),
    end_at: datetime = Query(...),
    include_scheduled: bool = Query(True),
    include_pending: bool = Query(False),
    include_procedures: bool = Query(True),
    appointment_ids: str | None = Query(None),
    procedure_ids: str | None = Query(None),
    current_user: User = Depends(require_doctor_user),
    db: Session = Depends(get_db),
):
    if end_at <= start_at:
        raise HTTPException(
            status_code=400,
            detail="El rango de fechas no es válido.",
        )

    appt_id_set = _parse_uuid_csv(appointment_ids)
    proc_id_set = _parse_uuid_csv(procedure_ids)
    selective = appt_id_set is not None or proc_id_set is not None

    if selective:
        if not appt_id_set and not proc_id_set:
            raise HTTPException(
                status_code=400,
                detail="Selecciona al menos un evento para exportar.",
            )
    elif not include_scheduled and not include_pending and not include_procedures:
        raise HTTPException(
            status_code=400,
            detail="Selecciona al menos un tipo de evento para exportar.",
        )

    content = IcalExportService.build_doctor_calendar(
        db,
        current_user.id,
        start_at,
        end_at,
        include_scheduled=include_scheduled,
        include_pending=include_pending,
        include_procedures=include_procedures,
        appointment_ids=appt_id_set,
        procedure_ids=proc_id_set,
    )
    return Response(
        content=content.encode("utf-8"),
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="keepi-agenda.ics"',
        },
    )


def _parse_uuid_csv(raw: str | None) -> set[UUID] | None:
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return set()
    return {UUID(part.strip()) for part in text.split(",") if part.strip()}


@router.post("/doctor/procedures", response_model=ProcedureBlockResponse)
async def create_doctor_procedure(
    body: ProcedureBlockCreateRequest,
    current_user: User = Depends(require_doctor_user),
    db: Session = Depends(get_db),
):
    return ProcedureBlockService.create(db, current_user.id, body)


@router.delete("/doctor/procedures/{block_id}", status_code=204)
async def delete_doctor_procedure(
    block_id: UUID,
    current_user: User = Depends(require_doctor_user),
    db: Session = Depends(get_db),
):
    ProcedureBlockService.delete(db, current_user.id, block_id)


@router.get("/mine", response_model=list[AppointmentResponse])
async def get_patient_appointments(
    current_user: User = Depends(require_patient_user),
    db: Session = Depends(get_db),
):
    return AppointmentService.list_patient_appointments(db, current_user.id)


@router.get("/{appointment_id}", response_model=AppointmentResponse)
async def get_appointment_detail(
    appointment_id: UUID,
    current_user: User = Depends(require_no_temp_password_user),
    db: Session = Depends(get_db),
):
    role_name = current_user.role.name if current_user.role else None
    return AppointmentService.get_appointment_for_user(
        db, appointment_id, current_user.id, role_name
    )


@router.post("/{appointment_id}/attendance", response_model=AppointmentResponse)
async def record_appointment_attendance(
    appointment_id: UUID,
    body: AppointmentAttendanceRequest,
    current_user: User = Depends(require_doctor_user),
    db: Session = Depends(get_db),
):
    row = AppointmentService.record_attendance(
        db,
        appointment_id,
        current_user.id,
        body.status,
    )
    return AppointmentResponse.from_entity(row)


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
        db, appointment_id, current_user.id, current_user.name or ""
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


@router.post("/{appointment_id}/doctor/reschedule", response_model=AppointmentResponse)
async def doctor_reschedule_web_appointment(
    appointment_id: UUID,
    body: AppointmentDoctorRescheduleRequest,
    current_user: User = Depends(require_doctor_user),
    db: Session = Depends(get_db),
):
    row = AppointmentService.doctor_reschedule_web_request(
        db,
        appointment_id,
        current_user.id,
        current_user.name or "",
        body,
    )
    return AppointmentResponse.from_entity(row)


@router.post(
    "/{appointment_id}/doctor/reassign-canceled",
    response_model=AppointmentResponse,
)
async def doctor_reassign_canceled_appointment(
    appointment_id: UUID,
    body: AppointmentDoctorProposeRequest,
    current_user: User = Depends(require_doctor_user),
    db: Session = Depends(get_db),
):
    row = AppointmentService.doctor_reassign_canceled_appointment(
        db,
        appointment_id,
        current_user.id,
        body,
        current_user.name or "",
    )
    return AppointmentResponse.from_entity(row)


public_router = APIRouter()


@public_router.get("/{token}", response_model=PublicAppointmentMetaResponse)
async def get_public_appointment_meta(
    token: str,
    db: Session = Depends(get_db),
):
    return AppointmentService.get_public_appointment_meta(db, token)


@public_router.post("/{token}/respond", response_model=PublicAppointmentRespondResponse)
async def respond_public_appointment(
    token: str,
    body: PublicAppointmentRespondRequest,
    db: Session = Depends(get_db),
):
    return AppointmentService.respond_public_appointment(db, token, body)