from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional, TYPE_CHECKING

import boto3
from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.prescription import (
    Prescription,
    PrescriptionConfirmRequest,
    PrescriptionDraftResponse,
    PrescriptionItem,
    PrescriptionItemIn,
    PrescriptionPatientResponse,
)
from app.repositories.prescription_repository import PrescriptionRepository
from app.repositories.user_repository import UserRepository
from app.utils.parsers.prescription_cedula_parser import procesar_receta_con_seguridad
from app.services.notificaciones.fcm_push_service import build_reminder_prompt_payload
from app.services.notificaciones.notification_service import NotificationService
from app.services.ocr.textract_service import extract_text_from_document
from app.utils.doctor_patient_storage import (
    build_receta_assigned_filename,
    doctor_patient_prescription_folder,
    patient_folder_label,
)

if TYPE_CHECKING:
    from app.services.documento.document_service import DocumentService

logger = logging.getLogger(__name__)

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
        route=item.get("via_administracion"),
    )


class PrescriptionService:
    def __init__(
        self,
        db: Session,
        prescription_repository: PrescriptionRepository | None = None,
        notification_service: NotificationService | None = None,
        document_service: "DocumentService | None" = None,
    ) -> None:
        self._db = db
        self._rx = prescription_repository or PrescriptionRepository(db)
        self._notifications = notification_service or NotificationService(db)
        self._document_service = document_service
        self._s3 = boto3.client(
            "s3",
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.aws_region,
        )

    def _to_patient_response(
        self, prescription: Prescription
    ) -> PrescriptionPatientResponse:
        items = self._rx.list_items_ordered(prescription.id)
        doctor_name = self._rx.get_doctor_name(prescription.doctor_id)
        return PrescriptionPatientResponse(
            id=str(prescription.id),
            doctor_name=doctor_name,
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

    async def create_draft_from_upload(
        self,
        *,
        doctor_id: uuid.UUID,
        patient_id: uuid.UUID,
        file: UploadFile,
    ) -> PrescriptionDraftResponse:
        content = await file.read()
        filename = file.filename or "receta"
        mime = file.content_type or "application/octet-stream"
        s3_key = f"prescriptions/{doctor_id}/{uuid.uuid4()}_{filename}"
        self._s3.put_object(
            Bucket=settings.aws_s3_bucket,
            Key=s3_key,
            Body=content,
            ContentType=mime,
        )
        if mime in ("image/jpeg", "image/png"):
            texto = await extract_text_from_document(file_bytes=content)
        elif mime == "application/pdf":
            texto = await extract_text_from_document(
                s3_bucket=settings.aws_s3_bucket, s3_key=s3_key
            )
        else:
            raise HTTPException(status_code=400, detail="Formato no soportado")

        parsed = procesar_receta_con_seguridad(texto or "")
        if parsed is None:
            raise HTTPException(
                status_code=403,
                detail="Receta no válida: no se detectó cédula profesional clara.",
            )
        item_dtos = [_map_item(x) for x in parsed]
        draft = Prescription(
            doctor_id=doctor_id,
            patient_id=patient_id,
            source_file_name=filename,
            source_file_type=mime,
            source_s3_key=s3_key,
            extracted_text=texto or "",
            status="draft_ocr",
        )
        orm_items = [
            PrescriptionItem(
                medication=d.medication,
                every_hours=d.every_hours,
                duration_days=d.duration_days,
                route=d.route,
                raw_payload={},
            )
            for d in item_dtos
        ]
        saved = self._rx.create_with_items(draft, orm_items)
        return PrescriptionDraftResponse(
            id=str(saved.id),
            patient_id=str(saved.patient_id),
            status=saved.status,
            filename=filename,
            extracted_text=saved.extracted_text or "",
            items=item_dtos,
        )

    async def confirm_prescription(
        self,
        *,
        prescription_id: uuid.UUID,
        doctor_id: uuid.UUID,
        doctor_name: str,
        body: PrescriptionConfirmRequest,
    ) -> PrescriptionPatientResponse:
        prescription = self._rx.get_by_id(prescription_id)
        if prescription is None:
            raise HTTPException(status_code=404, detail="Receta no encontrada")
        if prescription.doctor_id != doctor_id:
            raise HTTPException(status_code=403, detail="No autorizado")

        assigned_at = datetime.now(timezone.utc)
        prescription.extracted_text = body.extracted_text
        prescription.status = "published_to_patient"
        prescription.confirmed_at = assigned_at
        prescription.patient_reminders_enabled = False
        self._rx.save(prescription)

        self._rx.delete_items_for_prescription(prescription.id)
        for it in body.items:
            self._rx.add_item(
                PrescriptionItem(
                    prescription_id=prescription.id,
                    medication=it.medication,
                    every_hours=it.every_hours,
                    duration_days=it.duration_days,
                    route=it.route,
                    raw_payload={},
                )
            )

        await self._archive_prescription_on_assign(
            prescription=prescription,
            assigned_at=assigned_at,
        )

        reminder_payload = build_reminder_prompt_payload(doctor_name)
        self._notifications.notify_user_push_in_app(
            prescription.patient_id,
            title=reminder_payload["title"],
            message=reminder_payload["question"],
            notification_type="info",
            payload={"prescription_id": str(prescription.id), **reminder_payload},
            push_data={
                "prescription_id": str(prescription.id),
                "type": "prescription_assigned",
                "title": reminder_payload["title"],
                "question": reminder_payload["question"],
            },
        )
        prescription = self._rx.get_by_id(prescription_id)
        assert prescription is not None

        note_text = (body.doctor_note or "").strip()
        if note_text:
            from app.dto.timeline_dto import EventType
            from app.services.medical.doctor_timeline_note_service import (
                DoctorTimelineNoteService,
            )

            DoctorTimelineNoteService(self._db).save_note_for_event(
                doctor_id=doctor_id,
                patient_id=prescription.patient_id,
                timeline_event_id=f"pres_{prescription.id}",
                event_type=EventType.PRESCRIPTION.value,
                content=note_text,
            )

        return self._to_patient_response(prescription)

    async def _archive_prescription_on_assign(
        self,
        *,
        prescription: Prescription,
        assigned_at: datetime,
    ) -> None:
        source_key = (prescription.source_s3_key or "").strip()
        if not source_key:
            logger.warning(
                "Receta %s sin source_s3_key; no se archiva en carpeta del doctor",
                prescription.id,
            )
            return
        try:
            obj = self._s3.get_object(
                Bucket=settings.aws_s3_bucket,
                Key=source_key,
            )
            file_data = obj["Body"].read()
        except Exception:
            logger.exception(
                "No se pudo leer receta %s desde S3 (%s)",
                prescription.id,
                source_key,
            )
            return

        mime = prescription.source_file_type or "application/octet-stream"
        original = prescription.source_file_name or "receta"
        storage_name = build_receta_assigned_filename(
            assigned_at,
            content_type=mime,
            original_filename=original,
        )
        await self._archive_prescription_to_doctor_folder(
            doctor_id=prescription.doctor_id,
            patient_id=prescription.patient_id,
            file_data=file_data,
            file_name=original,
            file_type=mime,
            save_as_name=storage_name,
        )

    async def _archive_prescription_to_doctor_folder(
        self,
        *,
        doctor_id: uuid.UUID,
        patient_id: uuid.UUID,
        file_data: bytes,
        file_name: str,
        file_type: str,
        save_as_name: str,
    ) -> None:
        """Guarda la receta en S3 del doctor: {nombre_paciente}/Recetas."""
        if self._document_service is None:
            from app.factories.document_factory import (
                get_document_repository,
                get_folder_repository,
            )
            from app.services.documento.document_service import DocumentService

            self._document_service = DocumentService(
                db=self._db,
                document_repository=get_document_repository(self._db),
                folder_repository=get_folder_repository(self._db),
            )

        patient = UserRepository(self._db).get_by_id_plain(patient_id)
        patient_label = patient_folder_label(patient)
        category = doctor_patient_prescription_folder(patient_label)

        try:
            await self._document_service.save_analyzed_document(
                user_id=str(doctor_id),
                file_data=file_data,
                file_name=file_name,
                file_type=file_type,
                category=category,
                save_as_name=save_as_name,
                tags=["receta", f"patient:{patient_id}"],
            )
            logger.info(
                "Receta archivada en '%s' del doctor %s (paciente %s)",
                category,
                doctor_id,
                patient_id,
            )
        except Exception as exc:
            logger.exception(
                "Error archivando receta en '%s' del doctor %s: %s",
                category,
                doctor_id,
                exc,
            )

    def set_reminders_opt_in(
        self,
        *,
        prescription_id: uuid.UUID,
        patient_id: uuid.UUID,
        enabled: bool,
    ) -> PrescriptionPatientResponse:
        prescription = self._rx.get_by_id(prescription_id)
        if prescription is None or prescription.patient_id != patient_id:
            raise HTTPException(status_code=404, detail="Receta no encontrada")
        prescription.patient_reminders_enabled = enabled
        self._rx.save(prescription)
        prescription = self._rx.get_by_id(prescription_id)
        assert prescription is not None
        return self._to_patient_response(prescription)

    def list_for_patient(
        self, patient_id: uuid.UUID
    ) -> List[PrescriptionPatientResponse]:
        rows = self._rx.list_for_patient(patient_id)
        return [self._to_patient_response(p) for p in rows]

    def get_scan_presigned_url(
        self,
        *,
        prescription_id: uuid.UUID,
        current_user_id: uuid.UUID,
        role_name: Optional[str],
    ) -> dict:
        prescription = self._rx.get_by_id(prescription_id)
        if prescription is None:
            raise HTTPException(status_code=404, detail="Receta no encontrada")
        if role_name == "PATIENT" and prescription.patient_id == current_user_id:
            pass
        elif role_name == "DOCTOR" and prescription.doctor_id == current_user_id:
            pass
        else:
            raise HTTPException(status_code=403, detail="No autorizado")
        if not prescription.source_s3_key:
            raise HTTPException(status_code=404, detail="Sin archivo escaneado")
        url = self._s3.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": settings.aws_s3_bucket,
                "Key": prescription.source_s3_key,
                "ResponseContentDisposition": "inline",
            },
            ExpiresIn=3600,
        )
        return {"status": "success", "url": url}
