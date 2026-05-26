from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.core.roles import ROLE_DOCTOR, ROLE_PATIENT
from app.core.security import require_no_temp_password_user
from app.factories.medical_factory import get_prescription_service
from app.models.prescription import (
    PrescriptionConfirmRequest,
    PrescriptionDraftResponse,
    PrescriptionPatientResponse,
)
from app.models.user import User
from app.services.medical.prescription_service import PrescriptionService

router = APIRouter()


@router.post("/draft", response_model=PrescriptionDraftResponse)
async def create_prescription_draft(
    patient_id: UUID = Form(...),
    file: UploadFile = File(...),
    current_user: User = Depends(require_no_temp_password_user),
    svc: PrescriptionService = Depends(get_prescription_service),
):
    if current_user.role is None or current_user.role.name != ROLE_DOCTOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo DOCTOR puede asignar recetas",
        )
    return await svc.create_draft_from_upload(
        doctor_id=current_user.id,
        patient_id=patient_id,
        file=file,
    )


@router.put("/{prescription_id}/confirm", response_model=PrescriptionPatientResponse)
async def confirm_prescription(
    prescription_id: UUID,
    body: PrescriptionConfirmRequest,
    current_user: User = Depends(require_no_temp_password_user),
    svc: PrescriptionService = Depends(get_prescription_service),
):
    if current_user.role is None or current_user.role.name != ROLE_DOCTOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo DOCTOR puede confirmar recetas",
        )
    return await svc.confirm_prescription(
        prescription_id=prescription_id,
        doctor_id=current_user.id,
        doctor_name=current_user.name or "Doctor",
        body=body,
    )


@router.post(
    "/{prescription_id}/reminders-opt-in", response_model=PrescriptionPatientResponse
)
async def set_prescription_reminders(
    prescription_id: UUID,
    enabled: bool = Form(...),
    current_user: User = Depends(require_no_temp_password_user),
    svc: PrescriptionService = Depends(get_prescription_service),
):
    if current_user.role is None or current_user.role.name != ROLE_PATIENT:
        raise HTTPException(
            status_code=403, detail="Solo PATIENT puede responder recordatorios"
        )
    return svc.set_reminders_opt_in(
        prescription_id=prescription_id,
        patient_id=current_user.id,
        enabled=enabled,
    )


@router.get("/mine", response_model=List[PrescriptionPatientResponse])
async def list_my_prescriptions(
    current_user: User = Depends(require_no_temp_password_user),
    svc: PrescriptionService = Depends(get_prescription_service),
):
    if current_user.role is None or current_user.role.name != ROLE_PATIENT:
        raise HTTPException(status_code=403, detail="Solo PATIENT")
    return svc.list_for_patient(current_user.id)


@router.get("/{prescription_id}/scan-url")
async def get_prescription_scan_url(
    prescription_id: UUID,
    current_user: User = Depends(require_no_temp_password_user),
    svc: PrescriptionService = Depends(get_prescription_service),
):
    role_name = current_user.role.name if current_user.role else None
    return svc.get_scan_presigned_url(
        prescription_id=prescription_id,
        current_user_id=current_user.id,
        role_name=role_name,
    )
