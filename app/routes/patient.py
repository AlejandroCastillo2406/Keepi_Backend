"""Alias `/patient/*` del expediente (misma lógica que `/me/*`)."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_patient_user
from app.models.patient_medical_record import MedicalRecordPatch, MedicalRecordResponse
from app.models.user import User
from app.services.medical import MedicalRecordService

router = APIRouter()


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
