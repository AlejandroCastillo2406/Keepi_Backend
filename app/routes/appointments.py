from datetime import datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.models.appointment import AppointmentDoctorProposeRequest
from app.services.notificaciones.user_notify import notify_user_push_and_db
from app.core.database import get_db
from app.core.security import require_doctor_user, require_patient_user
from app.models.appointment import (
    Appointment,
    AppointmentCreateRequest,
    AppointmentResponse,
)
from app.models.user import User

router = APIRouter()

@router.post("/doctor", response_model=AppointmentResponse)
async def create_appointment(
    body: AppointmentCreateRequest,
    current_user: User = Depends(require_doctor_user),
    db: Session = Depends(get_db),
):
    start_at = body.appointment_date
    end_at = start_at + timedelta(minutes=body.duration_minutes)

    row = Appointment(
        doctor_id=current_user.id,
        patient_id=UUID(body.patient_id),
        appointment_date=start_at,
        end_date=end_at,
        status="scheduled",
        reason=body.reason.strip() or "Consulta médica",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.get("/doctor/calendar", response_model=list[AppointmentResponse])
async def get_doctor_calendar(
    start_at: datetime = Query(...),
    end_at: datetime = Query(...),
    current_user: User = Depends(require_doctor_user),
    db: Session = Depends(get_db),
):
    from sqlalchemy import or_ # Importante para poder usar el "OR"
    
    rows = (
        db.query(Appointment)
        .filter(Appointment.doctor_id == current_user.id)
        .filter(
            or_(
                Appointment.appointment_date == None, # Incluir las solicitudes sin fecha
                Appointment.appointment_date.between(start_at, end_at) # Y las que están en el mes actual
            )
        )
        .order_by(Appointment.created_at.desc())
        .all()
    )
    return rows


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
    return rows


@router.get("/{appointment_id}", response_model=AppointmentResponse)
async def get_appointment_detail(
    appointment_id: UUID,
    current_user: User = Depends(require_patient_user),
    db: Session = Depends(get_db),
):
    row = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if row is None or row.patient_id != current_user.id:
        raise HTTPException(status_code=404, detail="Cita no encontrada.")
    return row


@router.post("/{appointment_id}/doctor/propose", response_model=AppointmentResponse)
async def doctor_propose_time(
    appointment_id: UUID,
    body: AppointmentDoctorProposeRequest,
    current_user: User = Depends(require_doctor_user),
    db: Session = Depends(get_db),
):
    row = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if row is None or row.doctor_id != current_user.id:
        raise HTTPException(status_code=404, detail="Cita no encontrada.")

    start_at = body.proposed_start_at
    end_at = start_at + timedelta(minutes=body.duration_minutes)

    # Actualizamos la cita con la fecha y el nuevo estado
    row.appointment_date = start_at
    row.end_date = end_at
    row.status = "pending_patient_approval"
    
    db.commit()
    db.refresh(row)

    # Le enviamos la notificación al paciente
    notify_user_push_and_db(
        db,
        row.patient_id,
        title="Propuesta de cita",
        message=f"El Dr. {current_user.name} ha asignado una fecha para tu consulta.",
        notification_type="appointment_proposed",
        payload={"appointment_id": str(row.id), "action": "patient_decision"},
        push_data={"type": "appointment_proposed", "appointment_id": str(row.id)}
    )

    return row