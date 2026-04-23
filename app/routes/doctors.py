"""Endpoints exclusivos del flujo médico (alta de pacientes y gestión de citas)."""

from uuid import UUID
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.roles import ROLE_DOCTOR, ROLE_PATIENT
from app.core.security import require_no_temp_password_user
from app.models.user import DoctorCreatePatientRequest, DoctorCreatePatientResponse, User
from app.models.user import User as UserModel
from app.models.appointment import Appointment 
from app.services.usuarios import UserService

# IMPORTACIONES DEL TIMELINE
from app.repositories.patient_repository import PatientRepository
from app.dto.timeline_dto import TimelineEventResponse

# IMPORTACIONES NUEVAS PARA EL FLUJO DE CITAS
from app.models.appointment import AppointmentDoctorProposeRequest, AppointmentResponse
from app.services.medical.appointment_service import AppointmentService

router = APIRouter()
patient_repo = PatientRepository()

# ==========================================
# RUTAS DE PACIENTES
# ==========================================

@router.post("/patients", response_model=DoctorCreatePatientResponse)
async def create_patient_account(
    body: DoctorCreatePatientRequest,
    current_user: User = Depends(require_no_temp_password_user),
    db: Session = Depends(get_db),
):
    if current_user.role is None or current_user.role.name != ROLE_DOCTOR:
        raise HTTPException(status_code=403, detail="Solo usuarios con rol DOCTOR.")
    svc = UserService(db)
    try:
        patient, _plain_password = await svc.create_patient_by_doctor(
            current_user, body.email.strip(), body.name.strip(),
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return DoctorCreatePatientResponse(id=str(patient.id), email=patient.email, name=patient.name)

@router.get("/patients")
async def list_my_patients(
    current_user: User = Depends(require_no_temp_password_user),
    db: Session = Depends(get_db),
):
    svc = UserService(db)
    patient_role_id = svc.role_id_by_name(ROLE_PATIENT)
    rows = db.query(UserModel).filter(
        UserModel.created_by_user_id == current_user.id,
        UserModel.role_id == patient_role_id
    ).order_by(UserModel.created_at.desc()).all()
    return [{"id": str(u.id), "email": u.email, "name": u.name} for u in rows]

# ==========================================
# RUTAS DE CITAS
# ==========================================

# NUEVO ENDPOINT: Doctor propone hora de la cita
@router.post("/appointments/{appointment_id}/propose-time", response_model=AppointmentResponse)
async def propose_appointment_time(
    appointment_id: str,
    body: AppointmentDoctorProposeRequest,
    current_user: User = Depends(require_no_temp_password_user),
    db: Session = Depends(get_db),
):
    """El doctor asigna fecha y hora a la solicitud del paciente."""
    if current_user.role is None or current_user.role.name != ROLE_DOCTOR:
        raise HTTPException(status_code=403, detail="Solo usuarios con rol DOCTOR.")
        
    return AppointmentService.propose_doctor_time(db, appointment_id, str(current_user.id), body)

# ==========================================
# RUTA DE LÍNEA DE TIEMPO
# ==========================================

@router.get("/patients/{patient_id}/timeline", response_model=List[TimelineEventResponse])
async def get_patient_timeline(
    patient_id: UUID,
    current_user: User = Depends(require_no_temp_password_user),
    db: Session = Depends(get_db),
):
    """Obtiene el historial completo de eventos del paciente."""
    # Validar pertenencia
    patient = db.query(UserModel).filter(
        UserModel.id == patient_id,
        UserModel.created_by_user_id == current_user.id
    ).first()

    if not patient:
        raise HTTPException(status_code=404, detail="Paciente no vinculado a su cuenta.")

    # Llamar al repositorio real
    return patient_repo.get_timeline_events(db, str(patient_id))