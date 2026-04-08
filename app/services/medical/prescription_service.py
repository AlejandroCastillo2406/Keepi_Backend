"""Guardar receta en la nube del paciente (S3 o Drive según su configuración)."""

from __future__ import annotations

import io
import os
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.document import DocumentCreate
from app.models.user import User
from app.models.user_config import CloudProvider
from app.services.almacenamiento.drive_service import GoogleDriveService
from app.services.almacenamiento.s3_service import S3Service
from app.services.autenticacion import GoogleOAuthService
from app.services.documento.document_service import DocumentService
from app.services.medical.medical_record_service import MedicalRecordService
from app.services.usuarios.user_config_service import UserConfigService


class PrescriptionService:
    def __init__(self, db: Session):
        self._db = db
        self._mr = MedicalRecordService(db)

    async def save_to_patient_cloud(
        self,
        doctor: User,
        patient_id: UUID,
        file_bytes: bytes,
        filename: str,
        content_type: str,
        recordatorios: List[Dict[str, Any]],
        raw_text: str,
        next_appointment_at: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        patient = self._mr.assert_doctor_owns_patient(doctor, patient_id)
        uid = str(patient.id)

        cfg_svc = UserConfigService(self._db)
        cfg = await cfg_svc.get_or_create_user_config(uid)
        provider = cfg.cloud_provider
        if provider == CloudProvider.NOT_CONFIGURED:
            raise ValueError(
                "El paciente debe configurar Google Drive o Keepi Cloud antes de guardar recetas."
            )

        meta: Dict[str, Any] = {
            "tipo": "receta_medica",
            "recordatorios": recordatorios,
            "doctor_id": str(doctor.id),
            "doctor_name": doctor.name,
        }
        if next_appointment_at is not None:
            meta["next_appointment_at"] = next_appointment_at.isoformat()

        ai = {"tipo": "receta_medica", "recordatorios": recordatorios}
        doc_svc = DocumentService(self._db)
        base_name = os.path.basename(filename.replace("\\", "/"))
        display = f"Receta — {base_name}"

        if provider == CloudProvider.KEEPI_CLOUD:
            s3 = S3Service()
            bio = io.BytesIO(file_bytes)
            up = await s3.upload_document(
                uid, bio, filename, content_type or "application/octet-stream", folder="Recetas"
            )
            dc = DocumentCreate(
                name=display,
                category="Recetas",
                description="Receta médica en Keepi Cloud del paciente",
                file_name=filename,
                file_size=len(file_bytes),
                file_type=content_type,
                extracted_text=raw_text or None,
                cloud_provider="keepi_cloud",
                s3_key=up["file_path"],
                document_metadata=meta,
                ai_analysis=ai,
            )
            doc = await doc_svc.create_document(uid, dc)
            return {
                "document_id": str(doc.id),
                "storage": "keepi_cloud",
                "s3_key": up["file_path"],
            }

        if provider == CloudProvider.GOOGLE_DRIVE:
            oauth = GoogleOAuthService(self._db)
            creds = await oauth.refresh_user_tokens(uid)
            if not creds:
                raise ValueError(
                    "El paciente no ha conectado Google Drive. Debe iniciar sesión con Google en la app."
                )
            drive = GoogleDriveService(creds)
            folder_id = await drive.get_or_create_folder("Recetas", None)
            mime = content_type or "application/octet-stream"
            file_id = await drive.upload_file(file_bytes, base_name, folder_id, mime)
            dc = DocumentCreate(
                name=display,
                category="Recetas",
                description="Receta médica en Google Drive del paciente",
                file_name=filename,
                file_size=len(file_bytes),
                file_type=content_type,
                extracted_text=raw_text or None,
                cloud_provider="google_drive",
                drive_file_id=file_id,
                document_metadata=meta,
                ai_analysis=ai,
            )
            doc = await doc_svc.create_document(uid, dc)
            return {
                "document_id": str(doc.id),
                "storage": "google_drive",
                "drive_file_id": file_id,
            }

        raise ValueError(f"Proveedor de almacenamiento no soportado: {provider}")
