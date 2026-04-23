"""Alias `/patient/*` del expediente (misma lógica que `/me/*`)."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_patient_user
from app.dto.timeline_dto import TimelineEventResponse
from app.models.patient_medical_record import MedicalRecordPatch, MedicalRecordResponse
from app.models.user import User
from app.repositories.patient_repository import PatientRepository
from app.services.medical import MedicalRecordService

# IMPORTACIONES NUEVAS PARA EL FLUJO DE CITAS
from app.models.appointment import (
    AppointmentPatientCreateRequest, 
    AppointmentPatientRespondRequest, 
    AppointmentResponse
)
from app.services.medical.appointment_service import AppointmentService

router = APIRouter()
_patient_timeline_repo = PatientRepository()


@router.get("/medical-record", response_model=MedicalRecordResponse)
async def get_my_medical_record(
    patient: User = Depends(require_patient_user),
    db: Session = Depends(get_db),
):
    svc = MedicalRecordService(db)
    try:
        return svc.get_response_for_patient(patient)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.patch("/medical-record", response_model=MedicalRecordResponse)
async def patch_my_medical_record(
    body: MedicalRecordPatch,
    patient: User = Depends(require_patient_user),
    db: Session = Depends(get_db),
):
    svc = MedicalRecordService(db)
    try:
        return svc.patch_by_patient(patient, body)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.put("/medical-record", response_model=MedicalRecordResponse)
async def put_my_medical_record(
    body: MedicalRecordPatch,
    patient: User = Depends(require_patient_user),
    db: Session = Depends(get_db),
):
    svc = MedicalRecordService(db)
    try:
        return svc.patch_by_patient(patient, body)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

# ==========================================
# NUEVAS RUTAS DE CITAS (FLUJO PACIENTE)
# ==========================================

@router.post("/appointments/request", response_model=AppointmentResponse)
async def request_appointment(
    body: AppointmentPatientCreateRequest,
    patient: User = Depends(require_patient_user),
    db: Session = Depends(get_db),
):
    """El paciente envía una solicitud de cita solo con el motivo."""
    return AppointmentService.create_patient_request(db, str(patient.id), body)


@router.post("/appointments/{appointment_id}/respond", response_model=AppointmentResponse)
async def respond_to_appointment(
    appointment_id: str,
    body: AppointmentPatientRespondRequest,
    patient: User = Depends(require_patient_user),
    db: Session = Depends(get_db),
):
    """El paciente acepta o rechaza la fecha propuesta por el doctor."""
    return AppointmentService.respond_to_proposal(db, appointment_id, str(patient.id), body)

@router.get("/appointments", response_model=List[AppointmentResponse])
async def get_my_appointments(
    patient: User = Depends(require_patient_user),
    db: Session = Depends(get_db),
):
    """Obtiene todas las citas asociadas al paciente logueado."""
    return AppointmentService.get_appointments_by_patient(db, str(patient.id))


# ==========================================
# RUTA DE LÍNEA DE TIEMPO
# ==========================================

@router.get("/timeline", response_model=List[TimelineEventResponse])
async def get_my_care_timeline(
    patient: User = Depends(require_patient_user),
    db: Session = Depends(get_db),
):
    """Historial clínico-administrativo del paciente (cuenta, análisis, citas, recetas)."""
    return _patient_timeline_repo.get_timeline_events(db, str(patient.id))