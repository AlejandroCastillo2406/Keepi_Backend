"""Recursos del usuario autenticado bajo `/me/*` (OpenAPI y clientes móviles)."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.roles import ROLE_PATIENT
from app.core.security import require_no_temp_password_user
from app.models.patient_medical_record import MedicalRecordPatientUpdate, MedicalRecordResponse
from app.models.user import User
from app.services.patient_medical_record_service import PatientMedicalRecordService

router = APIRouter(prefix="/me", tags=["Me"])


def _require_patient(current_user: User) -> None:
    if current_user.role is None or current_user.role.name != ROLE_PATIENT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo los pacientes tienen expediente médico aquí.",
        )


@router.get("/medical-record", response_model=MedicalRecordResponse)
async def get_my_medical_record(
    current_user: User = Depends(require_no_temp_password_user),
    db: Session = Depends(get_db),
):
    """El paciente consulta su expediente."""
    _require_patient(current_user)
    svc = PatientMedicalRecordService(db)
    try:
        return svc.get_response_for_patient(current_user)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.put("/medical-record", response_model=MedicalRecordResponse)
async def put_my_medical_record(
    body: MedicalRecordPatientUpdate,
    current_user: User = Depends(require_no_temp_password_user),
    db: Session = Depends(get_db),
):
    """Actualización completa parcial (campos enviados)."""
    _require_patient(current_user)
    svc = PatientMedicalRecordService(db)
    try:
        return svc.update_for_patient(current_user, body)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.patch("/medical-record", response_model=MedicalRecordResponse)
async def patch_my_medical_record(
    body: MedicalRecordPatientUpdate,
    current_user: User = Depends(require_no_temp_password_user),
    db: Session = Depends(get_db),
):
    """Misma semántica que PUT; útil para clientes que usan PATCH."""
    _require_patient(current_user)
    svc = PatientMedicalRecordService(db)
    try:
        return svc.update_for_patient(current_user, body)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
