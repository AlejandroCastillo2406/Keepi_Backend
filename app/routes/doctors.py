"""Endpoints exclusivos del flujo médico (alta de pacientes)."""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.roles import ROLE_DOCTOR, ROLE_PATIENT
from app.core.security import require_no_temp_password_user
from app.models.patient_medical_record import MedicalRecordResponse
from app.models.user import DoctorCreatePatientRequest, DoctorCreatePatientResponse, User
from app.models.user import User as UserModel
from app.services.medical import MedicalRecordService
from app.services.medical.prescription_service import PrescriptionService
from app.services.notificaciones.patient_invite_email_service import send_patient_invite_email
from app.services.usuarios import UserService

router = APIRouter()


class RecetaConfirmPayload(BaseModel):
    recordatorios: List[Dict[str, Any]] = Field(default_factory=list)
    raw_text: str = ""
    next_appointment_at: Optional[datetime] = None


@router.post("/patients", response_model=DoctorCreatePatientResponse)
async def create_patient_account(
    body: DoctorCreatePatientRequest,
    current_user: User = Depends(require_no_temp_password_user),
    db: Session = Depends(get_db),
):
    """
    Crea cuenta de paciente con contraseña temporal y envío por correo.
    Requiere JWT con rol DOCTOR.
    """
    if current_user.role is None or current_user.role.name != ROLE_DOCTOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo usuarios con rol DOCTOR pueden crear pacientes.",
        )

    svc = UserService(db)
    try:
        patient, plain_password = await svc.create_patient_by_doctor(
            current_user,
            body.email.strip(),
            body.name.strip(),
            body.medical_record,
        )
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    email_result = send_patient_invite_email(patient.email, patient.name, plain_password)
    if not email_result.success:
        await svc.delete_user(str(patient.id))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"No se pudo enviar el correo: {email_result.error}",
        )

    return DoctorCreatePatientResponse(
        id=str(patient.id),
        email=patient.email,
        name=patient.name,
    )


@router.get("/patients")
async def list_my_patients(
    current_user: User = Depends(require_no_temp_password_user),
    db: Session = Depends(get_db),
):
    """Pacientes creados por el doctor autenticado."""
    if current_user.role is None or current_user.role.name != ROLE_DOCTOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo usuarios con rol DOCTOR.",
        )

    svc = UserService(db)
    patient_role_id = svc.role_id_by_name(ROLE_PATIENT)

    rows = (
        db.query(UserModel)
        .options(joinedload(UserModel.role))
        .filter(UserModel.created_by_user_id == current_user.id)
        .filter(UserModel.role_id == patient_role_id)
        .order_by(UserModel.created_at.desc())
        .all()
    )
    return [
        {
            "id": str(u.id),
            "email": u.email,
            "name": u.name,
            "must_change_password": u.must_change_password,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in rows
    ]


@router.get("/patients/{patient_id}/medical-record", response_model=MedicalRecordResponse)
async def get_patient_medical_record(
    patient_id: UUID,
    current_user: User = Depends(require_no_temp_password_user),
    db: Session = Depends(get_db),
):
    """Expediente de un paciente dado de alta por este médico."""
    if current_user.role is None or current_user.role.name != ROLE_DOCTOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo usuarios con rol DOCTOR.",
        )
    svc = MedicalRecordService(db)
    try:
        return svc.get_response_for_doctor(current_user, patient_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.post("/patients/{patient_id}/recetas")
async def guardar_receta_en_nube_paciente(
    patient_id: UUID,
    file: UploadFile = File(...),
    payload: str = Form(...),
    current_user: User = Depends(require_no_temp_password_user),
    db: Session = Depends(get_db),
):
    """
    Guarda la receta en la nube del **paciente** (Keepi Cloud o Google Drive) y registra el documento.
    """
    if current_user.role is None or current_user.role.name != ROLE_DOCTOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo usuarios con rol DOCTOR.",
        )
    try:
        body = RecetaConfirmPayload.model_validate(json.loads(payload))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Payload inválido: {e}")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archivo vacío.")

    svc = PrescriptionService(db)
    try:
        result = await svc.save_to_patient_cloud(
            current_user,
            patient_id,
            file_bytes,
            file.filename or "receta",
            file.content_type or "application/octet-stream",
            body.recordatorios,
            body.raw_text,
            body.next_appointment_at,
        )
        return {"status": "success", **result}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
