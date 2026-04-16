import uuid
from datetime import datetime, timezone
from typing import List
from uuid import UUID

import boto3
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.roles import ROLE_DOCTOR, ROLE_PATIENT
from app.core.security import require_no_temp_password_user
from app.models.notification import Notification, NotificationType
from app.models.prescription import (
    Prescription,
    PrescriptionConfirmRequest,
    PrescriptionDraftResponse,
    PrescriptionItem,
    PrescriptionItemIn,
    PrescriptionPatientResponse,
)
from app.models.user import User
from app.routes.archivo_routes import procesar_receta_con_seguridad
from app.services.notificaciones.fcm_push_service import (
    build_reminder_prompt_payload,
    send_push_to_user,
)
from app.services.ocr.textract_service import extract_text_from_document

router = APIRouter()
s3_client = boto3.client(
    "s3",
    aws_access_key_id=settings.aws_access_key_id,
    aws_secret_access_key=settings.aws_secret_access_key,
    region_name=settings.aws_region,
)


def _as_int_or_none(value: str | int | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def _map_item(item: dict) -> PrescriptionItemIn:
    return PrescriptionItemIn(
        medication=str(item.get("medicamento") or "").strip() or "No identificado",
        every_hours=_as_int_or_none(item.get("cada_cuantas_horas")),
        duration_days=_as_int_or_none(item.get("duracion_dias")),
        route=(item.get("via_administracion") or None),
    )


@router.post("/draft", response_model=PrescriptionDraftResponse)
async def create_prescription_draft(
    patient_id: UUID = Form(...),
    file: UploadFile = File(...),
    current_user: User = Depends(require_no_temp_password_user),
    db: Session = Depends(get_db),
):
    if current_user.role is None or current_user.role.name != ROLE_DOCTOR:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo DOCTOR puede asignar recetas")

    allowed = {"image/jpeg", "image/png", "application/pdf"}
    if file.content_type not in allowed:
        raise HTTPException(status_code=400, detail="Formato no soportado")

    file_bytes = await file.read()
    temp_key = f"prescriptions/{current_user.id}/{uuid.uuid4()}_{file.filename or 'receta'}"
    s3_client.put_object(
        Bucket=settings.aws_s3_bucket,
        Key=temp_key,
        Body=file_bytes,
        ContentType=file.content_type or "application/octet-stream",
    )

    if file.content_type == "application/pdf":
        texto_raw = await extract_text_from_document(s3_bucket=settings.aws_s3_bucket, s3_key=temp_key)
    else:
        texto_raw = await extract_text_from_document(file_bytes=file_bytes)

    parsed = procesar_receta_con_seguridad(texto_raw) or []
    items = [_map_item(i) for i in parsed]

    draft = Prescription(
        doctor_id=current_user.id,
        patient_id=patient_id,
        source_file_name=file.filename,
        source_file_type=file.content_type,
        source_s3_key=temp_key,
        extracted_text=texto_raw or "",
        status="draft_ocr",
    )
    db.add(draft)
    db.flush()
    for i in items:
        db.add(
            PrescriptionItem(
                prescription_id=draft.id,
                medication=i.medication,
                every_hours=i.every_hours,
                duration_days=i.duration_days,
                route=i.route,
                raw_payload=i.model_dump(),
            )
        )
    db.commit()
    return PrescriptionDraftResponse(
        id=str(draft.id),
        patient_id=str(patient_id),
        status=draft.status,
        filename=draft.source_file_name,
        extracted_text=draft.extracted_text or "",
        items=items,
    )


@router.put("/{prescription_id}/confirm", response_model=PrescriptionPatientResponse)
async def confirm_prescription(
    prescription_id: UUID,
    body: PrescriptionConfirmRequest,
    current_user: User = Depends(require_no_temp_password_user),
    db: Session = Depends(get_db),
):
    if current_user.role is None or current_user.role.name != ROLE_DOCTOR:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo DOCTOR puede confirmar recetas")

    prescription = db.query(Prescription).filter(Prescription.id == prescription_id).first()
    if prescription is None:
        raise HTTPException(status_code=404, detail="Receta no encontrada")
    if prescription.doctor_id != current_user.id:
        raise HTTPException(status_code=403, detail="No autorizado para esta receta")

    prescription.extracted_text = body.extracted_text
    prescription.status = "published_to_patient"
    prescription.confirmed_at = datetime.now(timezone.utc)
    prescription.patient_reminders_enabled = False

    db.query(PrescriptionItem).filter(PrescriptionItem.prescription_id == prescription.id).delete()
    for i in body.items:
        db.add(
            PrescriptionItem(
                prescription_id=prescription.id,
                medication=i.medication,
                every_hours=i.every_hours,
                duration_days=i.duration_days,
                route=i.route,
                raw_payload=i.model_dump(),
            )
        )

    doctor_name = current_user.name or "Doctor"
    reminder_payload = build_reminder_prompt_payload(doctor_name)
    db.add(
        Notification(
            user_id=prescription.patient_id,
            title=reminder_payload["title"],
            message=reminder_payload["question"],
            type=NotificationType.INFO,
            payload={"prescription_id": str(prescription.id), **reminder_payload},
        )
    )
    db.commit()
    db.refresh(prescription)
    send_push_to_user(
        db=db,
        user_id=str(prescription.patient_id),
        title=reminder_payload["title"],
        body=reminder_payload["question"],
        data={"prescription_id": str(prescription.id), "type": "prescription_assigned"},
    )
    return _to_patient_response(db, prescription)


@router.post("/{prescription_id}/reminders-opt-in", response_model=PrescriptionPatientResponse)
async def set_prescription_reminders(
    prescription_id: UUID,
    enabled: bool = Form(...),
    current_user: User = Depends(require_no_temp_password_user),
    db: Session = Depends(get_db),
):
    if current_user.role is None or current_user.role.name != ROLE_PATIENT:
        raise HTTPException(status_code=403, detail="Solo PATIENT puede responder recordatorios")
    prescription = db.query(Prescription).filter(Prescription.id == prescription_id).first()
    if prescription is None or prescription.patient_id != current_user.id:
        raise HTTPException(status_code=404, detail="Receta no encontrada")
    prescription.patient_reminders_enabled = enabled
    db.commit()
    db.refresh(prescription)
    return _to_patient_response(db, prescription)


@router.get("/mine", response_model=List[PrescriptionPatientResponse])
async def list_my_prescriptions(
    current_user: User = Depends(require_no_temp_password_user),
    db: Session = Depends(get_db),
):
    if current_user.role is None or current_user.role.name != ROLE_PATIENT:
        raise HTTPException(status_code=403, detail="Solo PATIENT")
    rows = (
        db.query(Prescription)
        .filter(Prescription.patient_id == current_user.id)
        .order_by(Prescription.created_at.desc())
        .all()
    )
    return [_to_patient_response(db, r) for r in rows]


@router.get("/{prescription_id}/scan-url")
async def get_prescription_scan_url(
    prescription_id: UUID,
    current_user: User = Depends(require_no_temp_password_user),
    db: Session = Depends(get_db),
):
    prescription = db.query(Prescription).filter(Prescription.id == prescription_id).first()
    if prescription is None:
        raise HTTPException(status_code=404, detail="Receta no encontrada")
    allowed = False
    if current_user.role and current_user.role.name == ROLE_PATIENT and prescription.patient_id == current_user.id:
        allowed = True
    if current_user.role and current_user.role.name == ROLE_DOCTOR and prescription.doctor_id == current_user.id:
        allowed = True
    if not allowed:
        raise HTTPException(status_code=403, detail="No autorizado")
    if not prescription.source_s3_key:
        raise HTTPException(status_code=404, detail="Receta sin archivo escaneado")
    url = s3_client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.aws_s3_bucket, "Key": prescription.source_s3_key, "ResponseContentDisposition": "inline"},
        ExpiresIn=60 * 30,
    )
    return {"status": "success", "url": url}


def _to_patient_response(db: Session, prescription: Prescription) -> PrescriptionPatientResponse:
    items = (
        db.query(PrescriptionItem)
        .filter(PrescriptionItem.prescription_id == prescription.id)
        .order_by(PrescriptionItem.created_at.asc())
        .all()
    )
    doctor = db.query(User).filter(User.id == prescription.doctor_id).first()
    return PrescriptionPatientResponse(
        id=str(prescription.id),
        doctor_name=doctor.name if doctor else None,
        status=prescription.status,
        source_file_name=prescription.source_file_name,
        confirmed_at=prescription.confirmed_at,
        reminders_enabled=prescription.patient_reminders_enabled,
        items=[
            PrescriptionItemIn(
                medication=i.medication,
                every_hours=i.every_hours,
                duration_days=i.duration_days,
                route=i.route,
            )
            for i in items
        ],
    )

