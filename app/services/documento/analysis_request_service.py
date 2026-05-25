from __future__ import annotations

import io
import logging
import uuid
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.dto.analysis_request_dto import AnalysisRequestCreate, AnalysisRequestResponse
from app.models.analysis_request import AnalysisRequest
from app.models.document import Document
from app.models.user import User
from app.repositories.analysis_request_invitation_repository import (
    AnalysisRequestInvitationRepository,
)
from app.repositories.analysis_request_repository import AnalysisRequestRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.user_repository import UserRepository
from app.services.almacenamiento import FolderService, GoogleDriveService, S3Service
from app.services.autenticacion import GoogleOAuthService
from app.services.notificaciones.analysis_upload_invite_email_service import (
    build_analysis_upload_email_html,
    build_analysis_upload_email_subject,
    build_public_analysis_upload_link,
)
from app.services.notificaciones.notification_service import NotificationService
from app.services.notificaciones.user_notify import (
    notify_user_push_and_db,
    notify_user_push_db_and_email,
)
from app.services.usuarios import UserConfigService

logger = logging.getLogger(__name__)
_MSG_ERROR_INTERNO = "Error interno del servidor"
_ANALYSIS_DOCUMENT_CATEGORY = "Análisis Clínicos"
_INVITATION_TTL_DAYS = 30


def _truncate(text: str, max_len: int) -> str:
    t = (text or "").strip()
    if len(t) <= max_len:
        return t
    return t[: max_len - 3] + "..."


class AnalysisRequestService:
    def __init__(
        self,
        db: Session,
        notification_service: NotificationService | None = None,
    ) -> None:
        self._db = db
        self._repo = AnalysisRequestRepository(db)
        self._invitations = AnalysisRequestInvitationRepository(db)
        self._docs = DocumentRepository(db)
        self._users = UserRepository(db)
        self._notifications = notification_service or NotificationService(db)

    def _notify_patient_new(
        self,
        *,
        patient: Optional[User],
        patient_id: UUID,
        doctor_id: UUID,
        analysis_request_id: UUID,
        description: str,
        public_link: Optional[str],
    ) -> None:
        doctor = self._users.get_by_id_plain(doctor_id)
        doctor_name = (doctor.name if doctor else None) or "Tu médico"
        patient_name = (patient.name if patient else None) or "Hola"
        patient_email = (patient.email if patient else None) or ""
        desc_preview = _truncate(description, 220)
        body = (
            f"{doctor_name} te pidió subir resultados: {desc_preview}"
            if desc_preview
            else f"{doctor_name} te envió una solicitud de análisis."
        )

        title = "Nueva solicitud de análisis"
        payload = {
            "analysis_request_id": str(analysis_request_id),
            "doctor_id": str(doctor_id),
            "description": description,
        }
        push_data = {
            "type": "analysis_request_assigned",
            "analysis_request_id": str(analysis_request_id),
            "doctor_id": str(doctor_id),
            "title": title,
            "body": body,
        }
        if public_link:
            payload["public_upload_link"] = public_link
            push_data["public_upload_link"] = public_link

        send_email = bool(patient_email and public_link)
        if send_email:
            email_html = build_analysis_upload_email_html(
                patient_name=patient_name,
                doctor_name=doctor_name,
                description=description,
                public_link=public_link,
                expires_in_days=_INVITATION_TTL_DAYS,
            )
            email_subject = build_analysis_upload_email_subject(doctor_name)
            try:
                res = notify_user_push_db_and_email(
                    self._db,
                    patient_id,
                    title=title,
                    message=body,
                    to_email=patient_email,
                    notification_type="info",
                    payload=payload,
                    push_data=push_data,
                    email_subject=email_subject,
                    email_html=email_html,
                )
                push_ok = res.push_devices_ok
                if not res.email or not res.email.success:
                    err = res.email.error if res.email else "no_response"
                    logger.warning(
                        "Email de solicitud %s a %s falló: %s",
                        analysis_request_id,
                        patient_email,
                        err,
                    )
            except Exception:
                logger.exception(
                    "No se pudo enviar email para solicitud %s; continuando con push",
                    analysis_request_id,
                )
                push_ok = self._fallback_push_only(
                    patient_id=patient_id,
                    title=title,
                    body=body,
                    payload=payload,
                    push_data=push_data,
                )
        else:
            push_ok = self._fallback_push_only(
                patient_id=patient_id,
                title=title,
                body=body,
                payload=payload,
                push_data=push_data,
            )

        if push_ok == 0:
            logger.warning(
                "Solicitud de análisis %s creada; push a 0 dispositivos para paciente %s.",
                analysis_request_id,
                patient_id,
            )

    def _fallback_push_only(
        self,
        *,
        patient_id: UUID,
        title: str,
        body: str,
        payload: Dict[str, Any],
        push_data: Dict[str, str],
    ) -> int:
        res = notify_user_push_and_db(
            self._db,
            patient_id,
            title=title,
            message=body,
            notification_type="info",
            payload=payload,
            push_data=push_data,
        )
        return res.push_devices_ok

    def _notify_doctor_completed(
        self, *, analysis_req: AnalysisRequest, document_id: UUID
    ) -> None:
        patient = self._users.get_by_id_plain(analysis_req.patient_id)
        patient_name = (patient.name if patient else None) or "Paciente"
        desc_preview = _truncate(analysis_req.description or "", 180)
        body = (
            f"{patient_name} completó la solicitud: {desc_preview}"
            if desc_preview
            else f"{patient_name} subió el estudio solicitado."
        )
        res = self._notifications.notify_user_push_in_app(
            analysis_req.doctor_id,
            title="Estudio completado",
            message=body,
            notification_type="info",
            payload={
                "analysis_request_id": str(analysis_req.id),
                "patient_id": str(analysis_req.patient_id),
                "document_id": str(document_id),
                "description": analysis_req.description or "",
            },
            document_id=document_id,
            push_data={
                "type": "analysis_request_completed",
                "analysis_request_id": str(analysis_req.id),
                "patient_id": str(analysis_req.patient_id),
                "document_id": str(document_id),
                "title": "Estudio completado",
                "body": body,
            },
        )
        if res.push_devices_ok == 0:
            logger.warning(
                "Solicitud %s completada; push a 0 dispositivos para doctor %s.",
                analysis_req.id,
                analysis_req.doctor_id,
            )

    def create_request(
        self, doctor_id: UUID, data: AnalysisRequestCreate
    ) -> AnalysisRequestResponse:
        created = self._repo.create(
            doctor_id=doctor_id,
            patient_id=data.patient_id,
            description=data.description,
        )

        patient = self._users.get_by_id_plain(data.patient_id)
        public_link: Optional[str] = None
        try:
            _, raw_token = self._invitations.create_invitation(
                analysis_request=created,
                patient_email=(patient.email if patient else None),
                patient_name=(patient.name if patient else None),
                ttl_days=_INVITATION_TTL_DAYS,
            )
            public_link = build_public_analysis_upload_link(raw_token)
        except Exception:
            logger.exception(
                "No se pudo crear invitación pública para solicitud %s; se envía sólo push",
                created.id,
            )

        self._notify_patient_new(
            patient=patient,
            patient_id=data.patient_id,
            doctor_id=doctor_id,
            analysis_request_id=created.id,
            description=data.description,
            public_link=public_link,
        )
        return created

    def get_pending_for_patient(
        self, patient_id: UUID
    ) -> List[AnalysisRequestResponse]:
        return self._repo.get_pending_by_patient(patient_id)

    def list_history_for_patient(
        self, patient_id: UUID
    ) -> List[AnalysisRequestResponse]:
        return self._repo.get_all_by_patient(patient_id)

    def complete_with_existing_document(
        self,
        *,
        patient_id: UUID,
        request_id: UUID,
        document_id: UUID,
    ) -> Dict[str, str]:
        analysis_req = self._repo.get_by_id(request_id)
        if (
            not analysis_req
            or analysis_req.patient_id != patient_id
            or analysis_req.status != "pending"
        ):
            raise HTTPException(
                status_code=404, detail="Solicitud no válida o ya completada."
            )
        doc = self._docs.get_by_id(str(document_id), str(patient_id))
        if not doc:
            raise HTTPException(
                status_code=404,
                detail="Documento no encontrado o no pertenece al usuario.",
            )
        updated = self._repo.mark_as_completed(request_id, document_id)
        if not updated:
            raise HTTPException(
                status_code=500, detail="No se pudo completar la solicitud."
            )
        self._notify_doctor_completed(analysis_req=updated, document_id=document_id)
        return {
            "message": "Solicitud completada.",
            "request_id": str(request_id),
            "document_id": str(document_id),
        }

    def get_public_upload_view(self, token: str) -> Dict[str, Any]:
        invitation = self._invitations.get_for_public_token(token)
        if not invitation:
            raise HTTPException(status_code=404, detail="Invitación no encontrada")

        analysis_req = self._repo.get_by_id(invitation.analysis_request_id)
        if not analysis_req:
            raise HTTPException(status_code=404, detail="Solicitud no encontrada")

        doctor = self._users.get_by_id_plain(invitation.doctor_id)
        doctor_name = (doctor.name if doctor else None) or "Tu doctor"

        effective_status = invitation.status
        if effective_status == "pending" and analysis_req.status != "pending":
            effective_status = "completed"

        return {
            "invitation_id": str(invitation.id),
            "analysis_request_id": str(invitation.analysis_request_id),
            "doctor_name": doctor_name,
            "patient_name": invitation.patient_name_snapshot or "",
            "description": analysis_req.description or "",
            "status": effective_status,
            "expires_at": invitation.expires_at,
        }

    async def _save_analysis_to_patient_s3(
        self,
        *,
        patient_uid: str,
        analysis_req: AnalysisRequest,
        content: bytes,
        filename: str,
        mime_type: str,
        extra_tags: Optional[List[str]] = None,
    ) -> Document:
        """Mismo almacenamiento que la subida web: S3 del paciente, cloud_provider=s3."""
        s3_service = S3Service()
        upload_res = await s3_service.upload_document(
            patient_uid,
            io.BytesIO(content),
            filename,
            mime_type,
            folder=_ANALYSIS_DOCUMENT_CATEGORY,
        )
        s3_key = upload_res.get("file_path")
        file_url = upload_res.get("signed_url")
        tags = [f"analysis_request:{analysis_req.id}"]
        if extra_tags:
            tags.extend(extra_tags)
        document = Document(
            user_id=UUID(patient_uid),
            name=filename,
            category=_ANALYSIS_DOCUMENT_CATEGORY,
            description=f"Archivo subido para solicitud: {analysis_req.description}",
            file_url=file_url,
            file_name=filename,
            file_size=len(content),
            file_type=mime_type.split("/")[0] if "/" in mime_type else mime_type,
            cloud_provider="s3",
            drive_file_id=None,
            s3_key=s3_key,
            tags=tags,
        )
        return self._docs.persist(document)

    async def upload_via_public_token(
        self,
        *,
        token: str,
        file: UploadFile,
    ) -> Dict[str, Any]:
        invitation = self._invitations.get_for_public_token(token)
        if not invitation:
            raise HTTPException(status_code=404, detail="Invitación no encontrada")
        if invitation.status == "expired":
            raise HTTPException(status_code=410, detail="El enlace ha expirado")
        if invitation.status == "completed":
            raise HTTPException(
                status_code=409, detail="Este enlace ya fue utilizado"
            )
        if invitation.status != "pending":
            raise HTTPException(status_code=400, detail="Enlace no disponible")

        analysis_req = self._repo.get_by_id(invitation.analysis_request_id)
        if not analysis_req:
            raise HTTPException(status_code=404, detail="Solicitud no encontrada")
        if analysis_req.status != "pending":
            raise HTTPException(
                status_code=409, detail="La solicitud ya fue completada"
            )

        patient_uid = str(invitation.patient_id)
        request_id = invitation.id

        try:
            content = await file.read()
            if not content:
                raise HTTPException(status_code=400, detail="El archivo está vacío")

            ext_from_mime = ""
            if file.content_type and "/" in file.content_type:
                ext_from_mime = file.content_type.split("/")[-1]
            filename = (
                file.filename
                or f"estudio_{request_id.hex}.{ext_from_mime or 'bin'}"
            )
            mime_type = file.content_type or "application/octet-stream"

            document = await self._save_analysis_to_patient_s3(
                patient_uid=patient_uid,
                analysis_req=analysis_req,
                content=content,
                filename=filename,
                mime_type=mime_type,
                extra_tags=["public_upload"],
            )

            updated_request = self._repo.mark_as_completed(
                analysis_req.id, document.id
            )
            if not updated_request:
                raise HTTPException(
                    status_code=500, detail="No se pudo completar la solicitud."
                )

            self._invitations.mark_completed(invitation.id)

            self._notify_doctor_completed(
                analysis_req=updated_request, document_id=document.id
            )

            return {
                "message": "Archivo subido y solicitud completada.",
                "request_id": str(updated_request.id),
                "document_id": str(document.id),
            }
        except HTTPException:
            raise
        except Exception:
            self._db.rollback()
            logger.exception("Error en upload_via_public_token")
            raise HTTPException(status_code=500, detail=_MSG_ERROR_INTERNO) from None

    async def doctor_upload_and_complete(
        self,
        *,
        doctor_id: UUID,
        request_id: UUID,
        file: UploadFile,
    ) -> Dict[str, Any]:
        analysis_req = self._repo.get_by_id(request_id)
        if (
            not analysis_req
            or str(analysis_req.doctor_id) != str(doctor_id)
            or analysis_req.status != "pending"
        ):
            raise HTTPException(
                status_code=404, detail="Solicitud no válida o ya completada."
            )
        try:
            content = await file.read()
            if not content:
                raise HTTPException(status_code=400, detail="El archivo está vacío")
            ext_from_mime = ""
            if file.content_type and "/" in file.content_type:
                ext_from_mime = file.content_type.split("/")[-1]
            filename = (
                file.filename
                or f"estudio_{request_id.hex}.{ext_from_mime or 'bin'}"
            )
            mime_type = file.content_type or "application/octet-stream"
            patient_uid = str(analysis_req.patient_id)

            document = await self._save_analysis_to_patient_s3(
                patient_uid=patient_uid,
                analysis_req=analysis_req,
                content=content,
                filename=filename,
                mime_type=mime_type,
                extra_tags=["doctor_upload"],
            )
            updated_request = self._repo.mark_as_completed(request_id, document.id)
            if not updated_request:
                raise HTTPException(
                    status_code=500, detail="No se pudo completar la solicitud."
                )
            self._notify_doctor_completed(
                analysis_req=updated_request, document_id=document.id
            )
            return {
                "message": "Archivo subido y solicitud completada.",
                "request_id": str(updated_request.id),
                "document_id": str(document.id),
            }
        except HTTPException:
            raise
        except Exception:
            self._db.rollback()
            logger.exception("Error en doctor_upload_and_complete")
            raise HTTPException(status_code=500, detail=_MSG_ERROR_INTERNO) from None

    async def upload_and_complete(
        self,
        *,
        patient_uid: str,
        request_id: UUID,
        file: UploadFile,
    ) -> Dict[str, Any]:
        repo = self._repo
        analysis_req = repo.get_by_id(request_id)
        if (
            not analysis_req
            or str(analysis_req.patient_id) != patient_uid
            or analysis_req.status != "pending"
        ):
            raise HTTPException(
                status_code=404, detail="Solicitud no válida o ya completada."
            )
        try:
            content = await file.read()
            filename = (
                file.filename
                or f"estudio_{request_id.hex}.{file.content_type.split('/')[-1]}"
            )
            mime_type = file.content_type or "application/octet-stream"

            config_service = UserConfigService(self._db)
            user_config = await config_service.get_or_create_user_config(patient_uid)

            cloud_provider = (
                user_config.cloud_provider.value
                if user_config and user_config.cloud_provider
                else "google_drive"
            )
            drive_file_id = None
            s3_key = None
            file_url = None

            folder_service = FolderService(self._db)
            folder_result = await folder_service.ensure_category_folder_exists(
                patient_uid, _ANALYSIS_DOCUMENT_CATEGORY, cloud_provider
            )
            if not folder_result.get("success"):
                if folder_result.get("requires_drive_auth"):
                    raise HTTPException(
                        status_code=401,
                        detail=folder_result.get("error", "Google Drive no autorizado"),
                    )
                raise HTTPException(
                    status_code=400,
                    detail=folder_result.get(
                        "error", "No se pudo preparar la carpeta de destino"
                    ),
                )

            if cloud_provider == "google_drive":
                oauth_service = GoogleOAuthService(self._db)
                credentials = await oauth_service.refresh_user_tokens(patient_uid)
                if not credentials:
                    raise HTTPException(
                        status_code=401, detail="Google Drive no autorizado"
                    )
                drive_folder_id = folder_result.get("folder_id")
                if not drive_folder_id:
                    raise HTTPException(
                        status_code=500, detail="No se obtuvo carpeta en Google Drive"
                    )
                drive_service = GoogleDriveService(credentials)
                drive_file_id = await drive_service.upload_file(
                    content, filename, drive_folder_id, mime_type
                )
                if drive_file_id:
                    file_url = f"https://drive.google.com/file/d/{drive_file_id}/view"
            else:
                s3_service = S3Service()
                folder_name = folder_result.get("folder_name") or "other"
                upload_res = await s3_service.upload_document(
                    patient_uid,
                    io.BytesIO(content),
                    filename,
                    mime_type,
                    folder=folder_name,
                )
                s3_key = upload_res.get("file_path")
                file_url = upload_res.get("signed_url")

            document = Document(
                user_id=UUID(patient_uid),
                name=filename,
                category=_ANALYSIS_DOCUMENT_CATEGORY,
                description=f"Archivo subido para solicitud: {analysis_req.description}",
                file_url=file_url,
                file_name=filename,
                file_size=len(content),
                file_type=mime_type.split("/")[0],
                cloud_provider=cloud_provider,
                drive_file_id=drive_file_id,
                s3_key=s3_key,
                tags=[f"analysis_request:{request_id}"],
            )
            self._docs.persist(document)

            updated_request = repo.mark_as_completed(request_id, document.id)
            if not updated_request:
                raise HTTPException(
                    status_code=500, detail="No se pudo completar la solicitud."
                )

            self._notify_doctor_completed(
                analysis_req=updated_request, document_id=document.id
            )

            return {
                "message": "Archivo subido y solicitud completada.",
                "request_id": str(updated_request.id),
                "document_id": str(document.id),
            }
        except HTTPException:
            raise
        except Exception:
            self._db.rollback()
            logger.exception("Error en upload_and_complete")
            raise HTTPException(status_code=500, detail=_MSG_ERROR_INTERNO) from None
