from __future__ import annotations

import base64
import json
import logging
import mimetypes
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import HTTPException, Request
from fastapi.responses import Response, RedirectResponse
from sqlalchemy.orm import Session

from app.exceptions import DriveAuthRequiredException
from app.services.almacenamiento import GoogleDriveService, S3Service
from app.services.autenticacion import GoogleOAuthService
from app.services.documento.document_service import DocumentService
from app.services.usuarios import UserConfigService, UserService

logger = logging.getLogger(__name__)
MSG_ERROR_INTERNO = "Error interno del servidor"


def _doc_on_storage(doc: Any, storage: str) -> bool:
    """Documento almacenado en la nube activa del usuario (sin exigir keepi_classified)."""
    doc_provider = getattr(doc, "cloud_provider", None) or ""
    if doc_provider:
        return doc_provider == storage
    if storage == "google_drive":
        return bool(getattr(doc, "drive_file_id", None))
    if storage == "keepi_cloud":
        return bool(getattr(doc, "s3_key", None)) and not getattr(
            doc, "drive_file_id", None
        )
    return False


def _parse_expiry_utc(raw: Any) -> Optional[datetime]:
    if raw is None:
        return None
    try:
        expiry = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if expiry.tzinfo is None:
            return expiry.replace(tzinfo=timezone.utc)
        return expiry.astimezone(timezone.utc)
    except Exception:
        return None


def _doc_to_alert_item(doc: Any, alert_status: str) -> dict:
    expiry = getattr(doc, "expiry_date", None)
    expiry_iso = expiry.isoformat() if expiry is not None else None
    return {
        "id": str(doc.id),
        "name": getattr(doc, "name", None) or getattr(doc, "file_name", None) or "Documento",
        "file_name": getattr(doc, "file_name", None),
        "category": getattr(doc, "category", None),
        "expiry_date": expiry_iso,
        "alert_status": alert_status,
        "cloud_provider": getattr(doc, "cloud_provider", None) or "",
        "keepi_document_id": str(doc.id),
        "can_edit_metadata": True,
    }


def _doc_matches_storage(doc: Any, storage: str) -> bool:
    if not (
        isinstance(getattr(doc, "ai_analysis", None), dict)
        and doc.ai_analysis.get("keepi_classified") is True
    ):
        return False
    doc_provider = getattr(doc, "cloud_provider", None) or ""
    if doc_provider:
        return doc_provider == storage
    if storage == "google_drive":
        return bool(getattr(doc, "drive_file_id", None))
    if storage == "keepi_cloud":
        return bool(getattr(doc, "s3_key", None)) and not getattr(
            doc, "drive_file_id", None
        )
    return False


def _s3_doc_to_file_item(doc: dict) -> dict:
    return {
        "id": doc.get("file_path", ""),
        "name": doc.get("filename", (doc.get("file_path", "") or "").split("/")[-1]),
        "size": str(doc.get("size", 0)),
        "keepi_verified": True,
        "can_edit_metadata": False,
    }


def _doc_to_keepi_file_fields(doc: Any) -> dict[str, Any]:
    ai = (
        doc.ai_analysis
        if isinstance(getattr(doc, "ai_analysis", None), dict)
        else {}
    )
    expiry = getattr(doc, "expiry_date", None)
    return {
        "keepi_document_id": str(doc.id),
        "category": getattr(doc, "category", None),
        "description": getattr(doc, "description", None),
        "expiry_date": expiry.isoformat() if expiry is not None else None,
        "document_number": ai.get("document_number"),
        "organization": ai.get("organization"),
        "can_edit_metadata": True,
    }


def _enrich_files_with_keepi_docs(files: list[dict], docs: list[Any], *, id_attr: str) -> None:
    by_external_id: dict[str, Any] = {}
    for doc in docs:
        external_id = getattr(doc, id_attr, None)
        if external_id:
            by_external_id[str(external_id)] = doc
    for file_item in files:
        doc = by_external_id.get(str(file_item.get("id", "")))
        if doc is not None:
            file_item.update(_doc_to_keepi_file_fields(doc))
        else:
            file_item.setdefault("can_edit_metadata", False)


async def _get_drive_service_or_raise(uid: str, db: Session) -> GoogleDriveService:
    oauth_service = GoogleOAuthService(db)
    credentials = await oauth_service.refresh_user_tokens(uid)
    if not credentials:
        authorization_url = None
        try:
            auth_data = await oauth_service.get_authorization_url(uid)
            authorization_url = auth_data.get("authorization_url")
        except Exception:
            logger.exception("No se pudo generar authorization_url para relink Drive")
        raise HTTPException(
            status_code=401,
            detail={
                "message": "Google Drive requiere autorizacion",
                "requires_drive_auth": True,
                "requires_action": "authorize",
                "authorization_url": authorization_url,
            },
        )
    return GoogleDriveService(credentials)


def decode_uid_from_request_safe(request: Request) -> str:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="No se envió el token")
    try:
        token = auth_header.split(" ")[1]
        payload_part = token.split(".")[1]
        payload_part += "=" * ((4 - len(payload_part) % 4) % 4)
        payload = json.loads(base64.b64decode(payload_part).decode("utf-8"))
        user_id = payload.get("sub") or payload.get("id") or payload.get("uid")
        if not user_id:
            raise ValueError()
        return str(user_id)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Token inválido") from exc


class DocumentApiService:
    def __init__(self, db: Session, document_service: DocumentService):
        self._db = db
        self._documents = document_service

    async def get_s3_folder_contents(self, uid: str, path: str) -> dict:
        if not path or (
            not path.startswith(f"users/{uid}/") and path != f"users/{uid}"
        ):
            raise HTTPException(status_code=403, detail="Ruta no permitida")
        s3 = S3Service()
        folder_suffix = path.replace(f"users/{uid}/", "", 1).strip("/")
        result = await s3.list_user_documents(
            uid, folder=folder_suffix if folder_suffix else None
        )
        documents = result.get("documents", [])
        subfolders = result.get("folders", [])
        folder_name = path.split("/")[-1] if "/" in path else "Keepi Cloud"
        files = [_s3_doc_to_file_item(d) for d in documents]
        s3_keys = [f["id"] for f in files if f.get("id")]
        if s3_keys:
            keepi_docs = self._documents.list_documents_by_s3_keys(uid, s3_keys)
            _enrich_files_with_keepi_docs(files, keepi_docs, id_attr="s3_key")
        folders_for_response = [
            {
                "id": f.get("path", f.get("name", "")).rstrip("/"),
                "name": f.get("name", ""),
                "files_count": 0,
            }
            for f in subfolders
        ]
        return {
            "folder": {"id": path, "name": folder_name},
            "folders": folders_for_response,
            "files": files,
        }

    async def get_keepi_cloud_root(self, uid: str) -> dict:
        config_service = UserConfigService(self._db)
        user_config = await config_service.get_or_create_user_config(uid)
        if not user_config or user_config.cloud_provider.value != "keepi_cloud":
            return {"folders": [], "root_files": []}
        s3_service = S3Service()
        user_prefix = f"users/{uid}/"
        s3_folders = await s3_service.list_folders(user_prefix)
        folders = [
            {
                "id": f["name"],
                "name": f["name"].split("/")[-1],
                "document_count": f.get("document_count", 0),
                "path": f["name"],
            }
            for f in s3_folders
        ]
        root_result = await s3_service.list_user_documents(uid)
        root_files = [
            _s3_doc_to_file_item(doc) for doc in root_result.get("documents", [])
        ]
        s3_keys = [f["id"] for f in root_files if f.get("id")]
        if s3_keys:
            keepi_docs = self._documents.list_documents_by_s3_keys(uid, s3_keys)
            _enrich_files_with_keepi_docs(root_files, keepi_docs, id_attr="s3_key")
        return {"folders": folders, "root_files": root_files}

    async def get_drive_folder_contents(self, uid: str, folder_id: str) -> dict:
        drive_service = await _get_drive_service_or_raise(uid, self._db)
        parent_id = None if folder_id == "root" else folder_id
        subfolders = await drive_service.get_folder_structure(parent_id)
        for folder in subfolders:
            files_in_folder = await drive_service.get_files_in_folder(folder["id"])
            folder["files_count"] = len(files_in_folder)
        files = await drive_service.get_files_in_folder(
            parent_id if parent_id is not None else "root"
        )
        file_ids = [f["id"] for f in files]
        if file_ids:
            docs = self._documents.list_documents_by_drive_file_ids(uid, file_ids)
            verified = {
                d.drive_file_id
                for d in docs
                if d.drive_file_id
                and isinstance(d.ai_analysis, dict)
                and d.ai_analysis.get("keepi_classified")
            }
            for f in files:
                f["keepi_verified"] = f["id"] in verified
                f.setdefault("can_edit_metadata", False)
            _enrich_files_with_keepi_docs(files, docs, id_attr="drive_file_id")
        else:
            for f in files:
                f["keepi_verified"] = False
                f["can_edit_metadata"] = False
        folder_name = "Mi unidad"
        if parent_id:
            try:
                meta = (
                    drive_service.service.files()
                    .get(fileId=parent_id, fields="name")
                    .execute()
                )
                folder_name = meta.get("name", folder_id)
            except Exception:
                folder_name = folder_id
        return {
            "folder": {"id": folder_id, "name": folder_name},
            "folders": subfolders,
            "files": files,
        }

    async def get_s3_file_view_url(self, uid: str, path: str) -> dict:
        if not path or not path.startswith(f"users/{uid}/"):
            raise HTTPException(status_code=403, detail="Ruta no permitida")
        s3_service = S3Service()
        try:
            url = await s3_service.get_file_url(path)
        except Exception as exc:
            logger.exception("Error generando URL S3 para %s", path)
            raise HTTPException(
                status_code=404,
                detail="No se pudo obtener la vista previa de este archivo.",
            ) from exc
        mime_type, _ = mimetypes.guess_type(path)
        file_name = path.split("/")[-1] if "/" in path else path
        return {
            "view_url": url,
            "download_url": url,
            "name": file_name,
            "mime_type": mime_type or "application/octet-stream",
        }

    async def get_drive_file_view_url(self, uid: str, file_id: str) -> dict:
        drive_service = await _get_drive_service_or_raise(uid, self._db)
        info = await drive_service.get_file_view_info(file_id)
        if not info.get("view_url"):
            raise HTTPException(
                status_code=404,
                detail="No se pudo obtener la URL de vista previa para este archivo.",
            )
        return info

    async def get_drive_file_content_response(self, uid: str, file_id: str) -> Response:
        drive_service = await _get_drive_service_or_raise(uid, self._db)
        file_content, file_name, mime_type = await drive_service.download_file(file_id)
        return Response(
            content=file_content,
            media_type=mime_type or "application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
        )

    async def delete_drive_file(self, uid: str, file_id: str) -> dict:
        drive_service = await _get_drive_service_or_raise(uid, self._db)
        success = await drive_service.delete_file(file_id)
        if not success:
            raise HTTPException(
                status_code=500, detail="No se pudo eliminar el archivo."
            )
        return {"success": True, "message": "Archivo eliminado"}

    async def get_mobile_dashboard(self, uid: str, limit: int) -> dict:
        user_service = UserService(self._db)
        user = await user_service.get_user_by_uid(uid)
        if not user:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        config_service = UserConfigService(self._db)
        user_config = await config_service.get_or_create_user_config(uid)
        storage_preference = (
            user_config.cloud_provider.value
            if user_config and user_config.cloud_provider
            else "google_drive"
        )
        all_documents = await self._documents.get_user_documents(uid)
        total_keepi = sum(
            1 for doc in all_documents if _doc_matches_storage(doc, storage_preference)
        )
        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(days=30)
        alerts: list[dict] = []
        for doc in all_documents:
            if not _doc_on_storage(doc, storage_preference):
                continue
            expiry = _parse_expiry_utc(getattr(doc, "expiry_date", None))
            if expiry is None:
                continue
            if expiry < now:
                alerts.append(_doc_to_alert_item(doc, "expired"))
            elif expiry <= cutoff:
                alerts.append(_doc_to_alert_item(doc, "expiring_soon"))
        alerts.sort(
            key=lambda item: (
                0 if item.get("alert_status") == "expired" else 1,
                item.get("expiry_date") or "",
            )
        )
        alerts_expired_count = sum(
            1 for item in alerts if item.get("alert_status") == "expired"
        )
        alerts_expiring_count = sum(
            1 for item in alerts if item.get("alert_status") == "expiring_soon"
        )
        folders = []
        root_files = []
        requires_drive_auth = False
        requires_action = None
        authorization_url = None
        if storage_preference == "keepi_cloud":
            s3_service = S3Service()
            try:
                user_prefix = f"users/{uid}/"
                s3_folders = await s3_service.list_folders(user_prefix)
                folders = [
                    {
                        "id": f["name"],
                        "name": f["name"].split("/")[-1],
                        "document_count": f.get("document_count", 0),
                        "path": f["name"],
                    }
                    for f in s3_folders
                ]
                root_result = await s3_service.list_user_documents(uid)
                root_files = [
                    _s3_doc_to_file_item(doc)
                    for doc in root_result.get("documents", [])
                ]
            except Exception:
                logger.exception("Error leyendo S3 en dashboard")
                folders = []
                root_files = []
        elif storage_preference == "google_drive":
            try:
                credentials = await GoogleOAuthService(self._db).refresh_user_tokens(
                    str(user.id)
                )
                if not credentials:
                    oauth_service = GoogleOAuthService(self._db)
                    auth_data = await oauth_service.get_authorization_url(str(user.id))
                    logger.warning(
                        "Usuario sin credenciales de Google Drive configuradas"
                    )
                    folders = []
                    requires_drive_auth = True
                    requires_action = "authorize"
                    authorization_url = auth_data.get("authorization_url")
                else:
                    drive_service = GoogleDriveService(credentials)
                    drive_folders = await drive_service.list_folders()
                    folders = [
                        {
                            "id": f["id"],
                            "name": f["name"],
                            "document_count": f.get("document_count", 0),
                            "path": f.get("path", ""),
                        }
                        for f in drive_folders
                    ]
            except Exception:
                logger.exception("Error leyendo carpetas de Drive")
                folders = []
        out: dict = {
            "folders": folders,
            "total_keepi": total_keepi,
            "alerts": alerts[:30],
            "alerts_count": len(alerts),
            "alerts_expired_count": alerts_expired_count,
            "alerts_expiring_count": alerts_expiring_count,
            "storage_preference": storage_preference,
            "expiring_soon_count": len(alerts),
            "expiring_soon": alerts[:20],
            "last_updated": datetime.now().isoformat(),
        }
        if storage_preference == "keepi_cloud":
            out["root_files"] = root_files
        if requires_drive_auth:
            out["requires_drive_auth"] = True
            out["requires_action"] = requires_action
            out["authorization_url"] = authorization_url
        return out

    def _document_to_metadata_payload(self, doc: Any) -> dict[str, Any]:
        ai = (
            doc.ai_analysis
            if isinstance(getattr(doc, "ai_analysis", None), dict)
            else {}
        )
        expiry = getattr(doc, "expiry_date", None)
        return {
            "id": str(doc.id),
            "name": getattr(doc, "name", None) or "",
            "file_name": getattr(doc, "file_name", None),
            "category": getattr(doc, "category", None) or "",
            "description": getattr(doc, "description", None),
            "expiry_date": expiry.isoformat() if expiry is not None else None,
            "document_number": ai.get("document_number"),
            "organization": ai.get("organization"),
            "drive_file_id": getattr(doc, "drive_file_id", None),
            "s3_key": getattr(doc, "s3_key", None),
            "cloud_provider": getattr(doc, "cloud_provider", None) or "",
        }

    async def get_mobile_document_metadata(
        self, uid: str, document_id: uuid.UUID
    ) -> dict[str, Any]:
        doc = self._documents._document_repository.get_by_id(str(document_id), uid)
        if not doc:
            raise HTTPException(status_code=404, detail="Documento no encontrado")
        return self._document_to_metadata_payload(doc)

    async def update_mobile_document_metadata(
        self,
        uid: str,
        document_id: uuid.UUID,
        *,
        name: Optional[str] = None,
        file_name: Optional[str] = None,
        category: Optional[str] = None,
        description: Optional[str] = None,
        expiry_date: Optional[datetime] = None,
        document_number: Optional[str] = None,
        organization: Optional[str] = None,
    ) -> dict[str, Any]:
        from app.models.document import DocumentUpdate as ModelDocumentUpdate

        doc = self._documents._document_repository.get_by_id(str(document_id), uid)
        if not doc:
            raise HTTPException(status_code=404, detail="Documento no encontrado")

        ai = dict(doc.ai_analysis) if isinstance(doc.ai_analysis, dict) else {}
        if document_number is not None:
            ai["document_number"] = document_number
        if organization is not None:
            ai["organization"] = organization

        update_fields: dict[str, Any] = {"ai_analysis": ai}
        if name is not None:
            update_fields["name"] = name.strip() or doc.name
        if file_name is not None:
            update_fields["file_name"] = file_name.strip() or doc.file_name
        if category is not None:
            update_fields["category"] = category.strip() or doc.category
        if description is not None:
            update_fields["description"] = description.strip() or None
        if expiry_date is not None:
            update_fields["expiry_date"] = expiry_date

        updated = await self._documents.update_document(
            str(document_id),
            uid,
            ModelDocumentUpdate(**update_fields),
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Documento no encontrado")
        raw = self._documents._document_repository.get_by_id(str(document_id), uid)
        return self._document_to_metadata_payload(raw)

    async def download_mobile_document(
        self, document_id: uuid.UUID
    ) -> Response | RedirectResponse:
        document = self._documents.get_document_by_id_any(document_id)
        if not document:
            raise HTTPException(status_code=404, detail="Documento no encontrado")
        cloud_provider = getattr(document, "cloud_provider", None) or ""
        file_path = getattr(document, "file_path", getattr(document, "s3_key", None))
        if cloud_provider == "google_drive":
            oauth_service = GoogleOAuthService(self._db)
            credentials = await oauth_service.refresh_user_tokens(str(document.user_id))
            if not credentials:
                raise HTTPException(
                    status_code=401, detail="El paciente revocó los permisos de Drive"
                )
            drive_service = GoogleDriveService(credentials)
            file_content, file_name, mime_type = await drive_service.download_file(
                str(document.drive_file_id)
            )
            return Response(
                content=file_content,
                media_type=mime_type or "application/octet-stream",
                headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
            )
        s3_service = S3Service()
        file_url = await s3_service.get_file_url(file_path)
        return RedirectResponse(url=file_url)
