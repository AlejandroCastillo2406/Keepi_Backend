"""Alias `/patient/*` del expediente (misma lógica que `/me/*`)."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_patient_user
from app.dto.timeline_dto import TimelineEventResponse
from app.models.health_questionnaire import (
    QuestionnaireForPatientResponse,
    QuestionnaireSubmitRequest,
)
from app.models.patient_medical_record import MedicalRecordPatch, MedicalRecordResponse
from app.models.user import User
from app.services.health_questionnaire_service import build_questionnaire_for_patient, submit_questionnaire
from app.repositories.patient_repository import PatientRepository
from app.services.medical import MedicalRecordService

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


@router.get("/health-questionnaire", response_model=QuestionnaireForPatientResponse)
async def get_my_health_questionnaire(
    patient: User = Depends(require_patient_user),
    db: Session = Depends(get_db),
):
    """Cuestionario de salud post-alta (paciente creado por médico)."""
    try:
        return build_questionnaire_for_patient(db, patient)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.post("/health-questionnaire/submit")
async def submit_my_health_questionnaire(
    body: QuestionnaireSubmitRequest,
    patient: User = Depends(require_patient_user),
    db: Session = Depends(get_db),
):
    try:
        submit_questionnaire(db, patient, body)
        return {"success": True}
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/timeline", response_model=List[TimelineEventResponse])
async def get_my_care_timeline(
    patient: User = Depends(require_patient_user),
    db: Session = Depends(get_db),
):
    """Historial clínico-administrativo del paciente (cuenta, análisis, citas, recetas)."""
    return _patient_timeline_repo.get_timeline_events(db, str(patient.id))


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
