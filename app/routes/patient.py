"""Expediente médico del paciente autenticado (lectura y edición)."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.roles import ROLE_PATIENT
from app.core.security import require_no_temp_password_user
from app.models.patient_medical_record import MedicalRecordPatientUpdate, MedicalRecordResponse
from app.models.user import User
from app.services.patient_medical_record_service import PatientMedicalRecordService

router = APIRouter()


@router.get("/medical-record", response_model=MedicalRecordResponse)
async def get_my_medical_record(
    current_user: User = Depends(require_no_temp_password_user),
    db: Session = Depends(get_db),
):
    """El paciente consulta su expediente."""
    if current_user.role is None or current_user.role.name != ROLE_PATIENT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo los pacientes tienen expediente médico aquí.",
        )
    svc = PatientMedicalRecordService(db)
    try:
        return svc.get_response_for_patient(current_user)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.put("/medical-record", response_model=MedicalRecordResponse)
async def update_my_medical_record(
    body: MedicalRecordPatientUpdate,
    current_user: User = Depends(require_no_temp_password_user),
    db: Session = Depends(get_db),
):
    """El paciente actualiza su expediente (campos enviados)."""
    if current_user.role is None or current_user.role.name != ROLE_PATIENT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo los pacientes pueden editar su expediente.",
        )
    svc = PatientMedicalRecordService(db)
    try:
        return svc.update_for_patient(current_user, body)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
