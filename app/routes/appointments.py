from datetime import datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_doctor_user, require_patient_user
from app.models.appointment import (
    Appointment,
    AppointmentActionRequest,
    AppointmentCreateRequest,
    AppointmentProposal,
    AppointmentProposalResponse,
    AppointmentResponse,
    AppointmentWithHistoryResponse,
)
from app.models.user import User
from app.services.notificaciones.user_notify import notify_user_push_and_db

router = APIRouter()

ACTIVE_STATUSES = {
    "pending_patient",
    "pending_patient_confirmation",
    "pending_doctor",
    "pending_doctor_review",
    "counter_doctor",
    "counter_proposed_by_doctor",
    "confirmed",
}


def _fmt_dt(value: datetime) -> str:
    dt = value.strftime("%d/%m/%Y %H:%M")
    return f"{dt} UTC"


def _to_response(row: Appointment) -> AppointmentResponse:
    latest = row.proposals[-1] if row.proposals else None
    current_start_at = latest.start_at if latest is not None else row.appointment_date
    current_end_at = latest.end_at if latest is not None else row.appointment_date + timedelta(minutes=30)
    proposed_by = latest.proposed_by if latest is not None else "doctor"
    notes = latest.notes if latest is not None else None
    version = len(row.proposals) if row.proposals else 1
    return AppointmentResponse(
        id=str(row.id),
        doctor_id=str(row.created_by_user_id),
        patient_id=str(row.patient_id),
        status=row.status,
        reason=row.reason,
        current_start_at=current_start_at,
        current_end_at=current_end_at,
        proposed_by=proposed_by,
        version=version,
        notes=notes,
        created_at=row.created_at,
        updated_at=row.created_at,
    )


def _to_response_with_history(row: Appointment) -> AppointmentWithHistoryResponse:
    base = _to_response(row)
    history = [
        AppointmentProposalResponse(
            id=str(p.id),
            appointment_id=str(p.appointment_id),
            proposed_by=p.proposed_by,
            start_at=p.start_at,
            end_at=p.end_at,
            notes=p.notes,
            sequence=p.sequence,
            created_at=p.created_at,
        )
        for p in row.proposals
    ]
    return AppointmentWithHistoryResponse(**base.model_dump(), proposals=history)


def _assert_doctor_slot_available(
    db: Session,
    *,
    doctor_id: UUID,
    start_at: datetime,
    end_at: datetime,
    exclude_appointment_id: UUID | None = None,
) -> None:
    rows = (
        db.query(Appointment)
        .filter(Appointment.created_by_user_id == doctor_id)
        .filter(Appointment.status.in_(tuple(ACTIVE_STATUSES)))
        .all()
    )
    for row in rows:
        if exclude_appointment_id is not None and row.id == exclude_appointment_id:
            continue
        latest = row.proposals[-1] if row.proposals else None
        row_start = latest.start_at if latest is not None else row.appointment_date
        row_end = latest.end_at if latest is not None else row.appointment_date + timedelta(minutes=30)
        if row_start < end_at and row_end > start_at:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="El doctor ya tiene una cita en ese horario.",
            )


def _append_proposal(
    db: Session,
    *,
    appointment: Appointment,
    proposed_by: str,
    start_at: datetime,
    end_at: datetime,
    notes: str | None,
) -> None:
    sequence = (len(appointment.proposals) if appointment.proposals else 0) + 1
    db.add(
        AppointmentProposal(
            appointment_id=appointment.id,
            proposed_by=proposed_by,
            start_at=start_at,
            end_at=end_at,
            notes=notes,
            sequence=sequence,
        )
    )


@router.post("/doctor", response_model=AppointmentResponse)
async def create_appointment(
    body: AppointmentCreateRequest,
    current_user: User = Depends(require_doctor_user),
    db: Session = Depends(get_db),
):
    start_at = body.appointment_date
    end_at = start_at + timedelta(minutes=body.duration_minutes)

    _assert_doctor_slot_available(db, doctor_id=current_user.id, start_at=start_at, end_at=end_at)

    row = Appointment(
        created_by_user_id=current_user.id,
        patient_id=UUID(body.patient_id),
        appointment_date=start_at,
        status="pending_patient",
        reason=body.reason.strip() or "Consulta médica",
    )
    db.add(row)
    db.flush()
    _append_proposal(
        db,
        appointment=row,
        proposed_by="doctor",
        start_at=start_at,
        end_at=end_at,
        notes=body.notes,
    )
    db.commit()
    db.refresh(row)

    notify_user_push_and_db(
        db,
        row.patient_id,
        title="Nueva cita agendada",
        message=(
            f"El Dr. {current_user.name} agendó una cita para el "
            f"{_fmt_dt(start_at)}."
        ),
        notification_type="appointment_created",
        payload={
            "appointment_id": str(row.id),
            "doctor_name": current_user.name,
            "proposed_start_at": start_at.isoformat(),
            "proposed_end_at": end_at.isoformat(),
            "reason": row.reason,
            "action": "patient_decision",
        },
        push_data={
            "type": "appointment_created",
            "appointment_id": str(row.id),
            "doctor_name": current_user.name,
            "action": "patient_decision",
        },
    )
    return _to_response(row)


@router.get("/doctor/calendar", response_model=list[AppointmentResponse])
async def get_doctor_calendar(
    start_at: datetime = Query(...),
    end_at: datetime = Query(...),
    current_user: User = Depends(require_doctor_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(Appointment)
        .filter(Appointment.created_by_user_id == current_user.id)
        .filter(Appointment.appointment_date >= start_at)
        .filter(Appointment.appointment_date < end_at)
        .order_by(Appointment.appointment_date.asc())
        .all()
    )
    return [_to_response(r) for r in rows]


@router.get("/mine", response_model=list[AppointmentResponse])
async def get_patient_appointments(
    current_user: User = Depends(require_patient_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(Appointment)
        .filter(Appointment.patient_id == current_user.id)
        .order_by(Appointment.appointment_date.desc())
        .all()
    )
    return [_to_response(r) for r in rows]


@router.get("/{appointment_id}", response_model=AppointmentWithHistoryResponse)
async def get_appointment_detail(
    appointment_id: UUID,
    current_user: User = Depends(require_patient_user),
    db: Session = Depends(get_db),
):
    row = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if row is None or row.patient_id != current_user.id:
        raise HTTPException(status_code=404, detail="Cita no encontrada.")
    return _to_response_with_history(row)


@router.post("/{appointment_id}/patient/confirm", response_model=AppointmentResponse)
async def patient_confirm_appointment(
    appointment_id: UUID,
    current_user: User = Depends(require_patient_user),
    db: Session = Depends(get_db),
):
    row = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if row is None or row.patient_id != current_user.id:
        raise HTTPException(status_code=404, detail="Cita no encontrada.")

    row.status = "confirmed"
    db.commit()
    db.refresh(row)

    notify_user_push_and_db(
        db,
        row.created_by_user_id,
        title="Cita confirmada por paciente",
        message=(
            "El paciente confirmó la cita del "
            f"{_fmt_dt(row.appointment_date)}."
        ),
        notification_type="appointment_confirmed",
        payload={"appointment_id": str(row.id), "status": row.status},
        push_data={"type": "appointment_confirmed", "appointment_id": str(row.id)},
    )
    return _to_response(row)


@router.post("/{appointment_id}/patient/request-change", response_model=AppointmentResponse)
async def patient_request_change(
    appointment_id: UUID,
    body: AppointmentActionRequest,
    current_user: User = Depends(require_patient_user),
    db: Session = Depends(get_db),
):
    row = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if row is None or row.patient_id != current_user.id:
        raise HTTPException(status_code=404, detail="Cita no encontrada.")
    row.status = "pending_doctor_review"
    db.commit()
    db.refresh(row)

    notify_user_push_and_db(
        db,
        row.created_by_user_id,
        title="Paciente no puede en ese horario",
        message=(
            "Tu paciente indicó que no puede asistir al horario del "
            f"{_fmt_dt(row.appointment_date)}. Propón una nueva hora."
        ),
        notification_type="appointment_change_requested",
        payload={
            "appointment_id": str(row.id),
            "status": row.status,
            "patient_notes": body.notes,
            "action": "doctor_review",
        },
        push_data={
            "type": "appointment_change_requested",
            "appointment_id": str(row.id),
            "status": row.status,
            "action": "doctor_review",
        },
    )
    return _to_response(row)


@router.post("/{appointment_id}/doctor/accept", response_model=AppointmentResponse)
async def doctor_accept_patient_proposal(
    appointment_id: UUID,
    current_user: User = Depends(require_doctor_user),
    db: Session = Depends(get_db),
):
    row = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if row is None or row.created_by_user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Cita no encontrada.")

    _assert_doctor_slot_available(
        db,
        doctor_id=current_user.id,
        start_at=row.appointment_date,
        end_at=row.appointment_date + timedelta(minutes=30),
        exclude_appointment_id=row.id,
    )

    row.status = "confirmed"
    db.commit()
    db.refresh(row)

    notify_user_push_and_db(
        db,
        row.patient_id,
        title="Doctor aceptó tu propuesta",
        message=(
            "Tu propuesta fue aceptada. Cita confirmada para el "
            f"{_fmt_dt(row.appointment_date)}."
        ),
        notification_type="appointment_confirmed",
        payload={"appointment_id": str(row.id), "status": row.status},
        push_data={"type": "appointment_confirmed", "appointment_id": str(row.id)},
    )
    return _to_response(row)


@router.post("/{appointment_id}/doctor/counter-propose", response_model=AppointmentResponse)
async def doctor_counter_propose(
    appointment_id: UUID,
    body: AppointmentActionRequest,
    current_user: User = Depends(require_doctor_user),
    db: Session = Depends(get_db),
):
    row = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if row is None or row.created_by_user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Cita no encontrada.")
    if body.proposed_start_at is None:
        raise HTTPException(status_code=400, detail="Debes enviar proposed_start_at.")

    new_end_at = body.proposed_start_at + timedelta(minutes=body.duration_minutes)
    _assert_doctor_slot_available(
        db,
        doctor_id=current_user.id,
        start_at=body.proposed_start_at,
        end_at=new_end_at,
        exclude_appointment_id=row.id,
    )

    row.appointment_date = body.proposed_start_at
    row.status = "counter_doctor"
    _append_proposal(
        db,
        appointment=row,
        proposed_by="doctor",
        start_at=body.proposed_start_at,
        end_at=new_end_at,
        notes=body.notes,
    )
    db.commit()
    db.refresh(row)

    notify_user_push_and_db(
        db,
        row.patient_id,
        title="Doctor propone nuevo horario",
        message=(
            "El doctor envió una contrapropuesta para el "
            f"{_fmt_dt(body.proposed_start_at)}."
        ),
        notification_type="appointment_counter_proposed",
        payload={
            "appointment_id": str(row.id),
            "proposed_start_at": body.proposed_start_at.isoformat(),
            "proposed_end_at": new_end_at.isoformat(),
            "action": "patient_decision",
        },
        push_data={
            "type": "appointment_counter_proposed",
            "appointment_id": str(row.id),
            "action": "patient_decision",
        },
    )
    return _to_response(row)
