"""Endpoints exclusivos del flujo médico (alta de pacientes)."""

import json
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.roles import ROLE_DOCTOR, ROLE_PATIENT
from app.core.security import require_no_temp_password_user
from app.models.patient_medical_record import MedicalRecordResponse
from app.models.user import DoctorCreatePatientRequest, DoctorCreatePatientResponse, User
from app.models.user import User as UserModel
from app.services.documento.document_service import DocumentService
from app.services.medical import MedicalRecordService
from app.services.notificaciones.patient_invite_email_service import send_patient_invite_email
from app.services.usuarios import UserService

router = APIRouter()


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


@router.post("/prescriptions/save")
async def save_prescription_after_review(
    patient_id: UUID = Form(...),
    file: UploadFile = File(...),
    medications_json: str = Form(
        ...,
        description='JSON array, ej. [{"medicamento":"...","cada_cuantas_horas":"8",...}]',
    ),
    extracted_text: Optional[str] = Form(None),
    next_appointment_at: Optional[str] = Form(
        None,
        description="Fecha/hora próxima cita (ISO8601), opcional",
    ),
    current_user: User = Depends(require_no_temp_password_user),
    db: Session = Depends(get_db),
):
    """
    Tras corroborar la extracción: sube el archivo a la nube del médico (S3 o Drive según configuración)
    y guarda el registro con medicación editada y opcionalmente la próxima cita.
    """
    if current_user.role is None or current_user.role.name != ROLE_DOCTOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo usuarios con rol DOCTOR.",
        )
    mrs = MedicalRecordService(db)
    try:
        mrs.assert_doctor_owns_patient(current_user, patient_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

    try:
        medications = json.loads(medications_json)
        if not isinstance(medications, list):
            raise ValueError("medications_json debe ser un array JSON")
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"medications_json inválido: {e}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    next_dt: Optional[datetime] = None
    if next_appointment_at and next_appointment_at.strip():
        try:
            next_dt = datetime.fromisoformat(next_appointment_at.strip().replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="next_appointment_at debe ser ISO8601 válido",
            )

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Archivo vacío")

    doc_svc = DocumentService(db)
    try:
        doc = await doc_svc.save_doctor_prescription_document(
            doctor_user_id=str(current_user.id),
            patient_id=str(patient_id),
            file_data=raw,
            file_name=file.filename or "receta.jpg",
            file_type=file.content_type or "application/octet-stream",
            medications=medications,
            extracted_text=extracted_text,
            next_appointment_at=next_dt,
        )
    except Exception as e:
        from app.exceptions import DriveAuthRequiredException

        if isinstance(e, DriveAuthRequiredException):
            raise HTTPException(
                status_code=401,
                detail={"requires_drive_auth": True, "message": str(e)},
            )
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "message": "Receta guardada en tu nube",
        "document_id": str(doc.id),
        "file_url": doc.file_url,
        "next_appointment_at": next_dt.isoformat() if next_dt else None,
    }
