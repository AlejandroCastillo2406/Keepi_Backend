import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, TypedDict

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.security import verify_token
from app.exceptions import DriveAuthRequiredException
from app.models.document import Document
from app.services.almacenamiento import GoogleDriveService, S3Service
from app.services.autenticacion import GoogleOAuthService
from app.services.documento import DocumentService
from app.services.usuarios import UserService, UserConfigService

logger = logging.getLogger(__name__)
router = APIRouter()

MSG_ERROR_INTERNO = "Error interno del servidor"


class TokenPayload(TypedDict, total=False):
    """Payload del JWT usado en verify_token."""
    uid: str
    email: Optional[str]
    name: Optional[str]


def _doc_matches_storage(doc: Any, storage: str) -> bool:
    """True si el documento cuenta como 'Con Keepi' para el almacenamiento dado."""
    if not (isinstance(getattr(doc, "ai_analysis", None), dict) and doc.ai_analysis.get("keepi_classified") is True):
        return False
    doc_provider = getattr(doc, "cloud_provider", None) or ""
    if doc_provider:
        return doc_provider == storage
    if storage == "google_drive":
        return bool(getattr(doc, "drive_file_id", None))
    if storage == "keepi_cloud":
        return bool(getattr(doc, "s3_key", None)) and not getattr(doc, "drive_file_id", None)
    return False


def _s3_doc_to_file_item(doc: dict) -> dict:
    """Formatea un documento S3 a el formato {id, name, size, keepi_verified}."""
    return {
        "id": doc.get("file_path", ""),
        "name": doc.get("filename", (doc.get("file_path", "") or "").split("/")[-1]),
        "size": str(doc.get("size", 0)),
        "keepi_verified": True,
    }


async def _get_drive_service_or_raise(uid: str) -> GoogleDriveService:
    """Obtiene GoogleDriveService con credenciales del usuario o lanza HTTPException 401."""
    oauth_service = GoogleOAuthService()
    credentials = await oauth_service.refresh_user_tokens(uid)
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Usuario no ha autorizado acceso a Google Drive.",
        )
    return GoogleDriveService(credentials)


@router.get("/s3/folders/contents")
async def get_s3_folder_contents(
    path: str = Query(..., description="Ruta de carpeta S3 (ej. users/{uid}/Documentos personales)"),
    user_token: TokenPayload = Depends(verify_token),
):
    """Contenido de una carpeta en Keepi Cloud (S3). path debe empezar con users/{uid}/."""
    try:
        uid = user_token["uid"]
        if not path or (not path.startswith(f"users/{uid}/") and path != f"users/{uid}"):
            raise HTTPException(status_code=403, detail="Ruta no permitida")
        s3 = S3Service()
        folder_suffix = path.replace(f"users/{uid}/", "", 1).strip("/")
        result = await s3.list_user_documents(uid, folder=folder_suffix if folder_suffix else None)
        documents = result.get("documents", [])
        subfolders = result.get("folders", [])
        folder_name = path.split("/")[-1] if "/" in path else "Keepi Cloud"
        files = [_s3_doc_to_file_item(d) for d in documents]
        folders_for_response = [
            {"id": f.get("path", f.get("name", "")).rstrip("/"), "name": f.get("name", ""), "files_count": 0}
            for f in subfolders
        ]
        return {
            "folder": {"id": path, "name": folder_name},
            "folders": folders_for_response,
            "files": files,
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error leyendo contenido S3")
        raise HTTPException(status_code=500, detail=MSG_ERROR_INTERNO)


@router.get("/keepi-cloud/root")
async def get_keepi_cloud_root(
    user_token: TokenPayload = Depends(verify_token),
):
    """Contenido raíz de Keepi Cloud (S3) del usuario: subcarpetas y archivos en users/{uid}/."""
    try:
        uid = user_token["uid"]
        config_service = UserConfigService()
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
        root_files = [_s3_doc_to_file_item(doc) for doc in root_result.get("documents", [])]
        logger.info("keepi-cloud/root uid=%s prefix=%s folders=%s root_files=%s", uid, user_prefix, len(folders), len(root_files))
        return {"folders": folders, "root_files": root_files}
    except Exception:
        logger.exception("Error leyendo Keepi Cloud root")
        raise HTTPException(status_code=500, detail=MSG_ERROR_INTERNO)


@router.get("/drive/folders/{folder_id}/contents")
async def get_drive_folder_contents(
    folder_id: str,
    user_token: TokenPayload = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """Obtener contenido de una carpeta: subcarpetas y archivos."""
    try:
        drive_service = await _get_drive_service_or_raise(user_token["uid"])
        parent_id = None if folder_id == "root" else folder_id

        subfolders = await drive_service.get_folder_structure(parent_id)
        for folder in subfolders:
            files_in_folder = await drive_service.get_files_in_folder(folder["id"])
            folder["files_count"] = len(files_in_folder)

        files = await drive_service.get_files_in_folder(parent_id if parent_id is not None else "root")
        file_ids = [f["id"] for f in files]
        if file_ids:
            user_uuid = uuid.UUID(user_token["uid"])
            docs = db.query(Document).filter(
                Document.user_id == user_uuid,
                Document.drive_file_id.in_(file_ids),
            ).all()
            verified = {
                d.drive_file_id for d in docs
                if d.drive_file_id and isinstance(d.ai_analysis, dict) and d.ai_analysis.get("keepi_classified")
            }
            for f in files:
                f["keepi_verified"] = f["id"] in verified
        else:
            for f in files:
                f["keepi_verified"] = False

        folder_name = "Mi unidad"
        if parent_id:
            try:
                meta = drive_service.service.files().get(fileId=parent_id, fields="name").execute()
                folder_name = meta.get("name", folder_id)
            except Exception:
                folder_name = folder_id

        return {
            "folder": {"id": folder_id, "name": folder_name},
            "folders": subfolders,
            "files": files,
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error listando contenido Drive")
        raise HTTPException(status_code=500, detail=MSG_ERROR_INTERNO)


@router.get("/drive/files/{file_id}/view-url")
async def get_drive_file_view_url(
    file_id: str,
    user_token: TokenPayload = Depends(verify_token),
):
    """Obtener URL para vista previa/descarga de un archivo de Google Drive."""
    try:
        drive_service = await _get_drive_service_or_raise(user_token["uid"])
        info = await drive_service.get_file_view_info(file_id)
        if not info.get("view_url"):
            raise HTTPException(status_code=404, detail="No se pudo obtener la URL de vista previa para este archivo.")
        return info
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error obteniendo URL de vista Drive")
        raise HTTPException(status_code=500, detail=MSG_ERROR_INTERNO)


@router.get("/drive/files/{file_id}/content")
async def get_drive_file_content(
    file_id: str,
    user_token: TokenPayload = Depends(verify_token),
):
    """Descargar contenido del archivo de Google Drive (para guardar en dispositivo)."""
    try:
        drive_service = await _get_drive_service_or_raise(user_token["uid"])
        file_content, file_name, mime_type = await drive_service.download_file(file_id)
        return Response(
            content=file_content,
            media_type=mime_type or "application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error descargando archivo Drive")
        raise HTTPException(status_code=500, detail=MSG_ERROR_INTERNO)


@router.delete("/drive/files/{file_id}")
async def delete_drive_file(
    file_id: str,
    user_token: TokenPayload = Depends(verify_token),
):
    """Eliminar archivo de Google Drive (permanente)."""
    try:
        drive_service = await _get_drive_service_or_raise(user_token["uid"])
        success = await drive_service.delete_file(file_id)
        if not success:
            raise HTTPException(status_code=500, detail="No se pudo eliminar el archivo.")
        return {"success": True, "message": "Archivo eliminado"}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error eliminando archivo Drive")
        raise HTTPException(status_code=500, detail=MSG_ERROR_INTERNO)


@router.get("/mobile/dashboard")
async def get_mobile_dashboard(
    user_token: TokenPayload = Depends(verify_token),
    limit: int = Query(10, description="Número de documentos a mostrar"),
):
    """Dashboard optimizado para móviles con información resumida"""
    try:
        user_service = UserService()
        user = await user_service.get_user_by_uid(user_token["uid"])
        if not user:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")

        config_service = UserConfigService()
        user_config = await config_service.get_or_create_user_config(user_token["uid"])
        storage_preference = user_config.cloud_provider.value if user_config and user_config.cloud_provider else "google_drive"

        document_service = DocumentService()
        all_documents = await document_service.get_user_documents(user_token["uid"])

        total_keepi = sum(1 for doc in all_documents if _doc_matches_storage(doc, storage_preference))

        expiring_soon = []
        for doc in all_documents:
            if doc.expiry_date:
                try:
                    expiry = datetime.fromisoformat(str(doc.expiry_date).replace("Z", "+00:00"))
                    if expiry <= datetime.now(timezone.utc) + timedelta(days=30):
                        expiring_soon.append(doc)
                except Exception:
                    continue

        folders = []
        root_files = []
        if storage_preference == "keepi_cloud":
            s3_service = S3Service()
            try:
                user_prefix = f"users/{user_token['uid']}/"
                s3_folders = await s3_service.list_folders(user_prefix)
                folders = [
                    {"id": f["name"], "name": f["name"].split("/")[-1], "document_count": f.get("document_count", 0), "path": f["name"]}
                    for f in s3_folders
                ]
                root_result = await s3_service.list_user_documents(user_token["uid"])
                root_files = [_s3_doc_to_file_item(doc) for doc in root_result.get("documents", [])]
            except Exception:
                logger.exception("Error leyendo S3 en dashboard")
                folders = []
                root_files = []

        elif storage_preference == "google_drive":
            try:
                credentials = await GoogleOAuthService().refresh_user_tokens(str(user.id))
                if not credentials:
                    logger.warning("Usuario sin credenciales de Google Drive configuradas")
                    folders = []
                else:
                    drive_service = GoogleDriveService(credentials)
                    drive_folders = await drive_service.list_folders()
                    folders = [
                        {"id": f["id"], "name": f["name"], "document_count": f.get("document_count", 0), "path": f.get("path", "")}
                        for f in drive_folders
                    ]
            except Exception:
                logger.exception("Error leyendo carpetas de Drive")
                folders = []

        out = {
            "folders": folders,
            "total_keepi": total_keepi,
            "expiring_soon_count": len(expiring_soon),
            "expiring_soon": expiring_soon[:20],
            "last_updated": datetime.now().isoformat(),
        }
        if storage_preference == "keepi_cloud":
            out["root_files"] = root_files
        return out
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error en mobile dashboard")
        raise HTTPException(status_code=500, detail=MSG_ERROR_INTERNO)


@router.post("/mobile/analyze")
async def mobile_analyze_document(
    file: UploadFile = File(...),
    user_token: TokenPayload = Depends(verify_token),
):
    """Paso 1: Solo analizar archivo con Bedrock. No guarda. Devuelve resumen para el modal."""
    user_id = user_token.get("uid", "unknown")
    logger.info("[mobile/analyze] Solicitud recibida: usuario=%s, archivo=%s", user_id, file.filename)
    try:
        if not file.filename:
            logger.warning("[mobile/analyze] Archivo sin nombre")
            raise HTTPException(status_code=400, detail="Nombre de archivo requerido")
        content = await file.read()
        logger.info("[mobile/analyze] Archivo leído: %s bytes. Iniciando análisis Bedrock...", len(content))
        document_service = DocumentService()
        result = await document_service.analyze_document_only(
            user_token["uid"],
            content,
            file.filename,
            file.content_type or "application/octet-stream",
        )
        if result.get("subscription_required"):
            logger.info("[mobile/analyze] Respuesta 402: suscripción requerida para usuario=%s", user_id)
            return JSONResponse(status_code=402, content=result)
        logger.info("[mobile/analyze] Análisis completado para usuario=%s, categoría=%s", user_id, result.get("category"))
        return result
    except HTTPException:
        raise
    except Exception:
        logger.exception("[mobile/analyze] Error analizando documento")
        raise HTTPException(status_code=500, detail=MSG_ERROR_INTERNO)


@router.post("/mobile/save-analyzed")
async def mobile_save_analyzed_document(
    file: UploadFile = File(...),
    category: str = Form(...),
    file_name: str = Form(..., description="Nombre con el que se guardará el archivo"),
    expiry_date: Optional[str] = Form(None),
    document_number: Optional[str] = Form(None),
    organization: Optional[str] = Form(None),
    user_token: TokenPayload = Depends(verify_token),
):
    """Paso 2: Guardar archivo ya analizado en la carpeta de la categoría (crear carpeta si no existe)."""
    try:
        if not file.filename:
            raise HTTPException(status_code=400, detail="Nombre de archivo requerido")
        content = await file.read()
        parsed_expiry = None
        if expiry_date:
            try:
                parsed_expiry = datetime.fromisoformat(expiry_date.replace("Z", "+00:00"))
            except ValueError:
                pass
        document_service = DocumentService()
        document = await document_service.save_analyzed_document(
            user_id=user_token["uid"],
            file_data=content,
            file_name=file.filename,
            file_type=file.content_type or "application/octet-stream",
            category=category.strip(),
            save_as_name=file_name.strip() or file.filename,
            expiry_date=parsed_expiry,
            document_number=document_number or None,
            organization=organization or None,
            tags=None,
        )
        return {
            "message": "Documento guardado correctamente",
            "document_id": str(document.id),
            "category": document.category,
            "file_name": document.file_name,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        if isinstance(e, DriveAuthRequiredException):
            raise HTTPException(status_code=401, detail={"requires_drive_auth": True, "message": str(e)})
        logger.exception("Error guardando documento analizado")
        raise HTTPException(status_code=500, detail=MSG_ERROR_INTERNO)
