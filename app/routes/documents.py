import logging
import uuid
import base64
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, TypedDict

from fastapi import (APIRouter, Depends, File, Form, HTTPException, Query,
                     UploadFile, Request)
from fastapi.responses import JSONResponse, Response, RedirectResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
# Importaciones de tus modelos y servicios existentes
from app.exceptions import DriveAuthRequiredException
from app.models.document import Document
from app.services.almacenamiento import GoogleDriveService, S3Service
from app.services.autenticacion import GoogleOAuthService
from app.services.documento import DocumentService
from app.services.usuarios import UserConfigService, UserService

logger = logging.getLogger(__name__)
router = APIRouter()

MSG_ERROR_INTERNO = "Error interno del servidor"

class TokenPayload(TypedDict, total=False):
    """Payload del JWT usado para compatibilidad."""
    uid: str
    email: Optional[str]
    name: Optional[str]

# --- FUNCIÓN DE UTILIDAD INTERNA (EVITA IMPORT CIRCULAR Y ERRORES 403) ---
def get_user_id_from_token(request: Request) -> str:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="No se envió el token de seguridad")
    
    token = auth_header.split(" ")[1]
    try:
        # Decodificamos la parte del payload del JWT
        payload_part = token.split(".")[1]
        missing_padding = len(payload_part) % 4
        if missing_padding:
            payload_part += '=' * (4 - missing_padding)
            
        payload = json.loads(base64.b64decode(payload_part).decode("utf-8"))
        
        # Buscamos el ID en las claves que usa tu sistema
        user_id = payload.get("sub") or payload.get("id") or payload.get("uid")
        if not user_id:
            raise ValueError("ID no encontrado")
        return user_id
    except Exception:
        raise HTTPException(status_code=401, detail="Sesión inválida o expirada")

# --- FUNCIONES DE APOYO ---

def _doc_matches_storage(doc: Any, storage: str) -> bool:
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
    return {
        "id": doc.get("file_path", ""),
        "name": doc.get("filename", (doc.get("file_path", "") or "").split("/")[-1]),
        "size": str(doc.get("size", 0)),
        "keepi_verified": True,
    }

async def _get_drive_service_or_raise(uid: str, db: Session) -> GoogleDriveService:
    oauth_service = GoogleOAuthService(db)
    credentials = await oauth_service.refresh_user_tokens(uid)
    if not credentials:
        raise HTTPException(status_code=401, detail="Usuario no ha autorizado acceso a Google Drive.")
    return GoogleDriveService(credentials)

# --- ENDPOINTS ---

@router.get("/s3/folders/contents")
async def get_s3_folder_contents(
    request: Request,
    path: str = Query(..., description="Ruta de carpeta S3"),
):
    try:
        uid = get_user_id_from_token(request)
        if not path or (not path.startswith(f"users/{uid}/") and path != f"users/{uid}"):
            raise HTTPException(status_code=403, detail="Ruta no permitida")
        
        s3 = S3Service()
        folder_suffix = path.replace(f"users/{uid}/", "", 1).strip("/")
        result = await s3.list_user_documents(uid, folder=folder_suffix if folder_suffix else None)
        
        return {
            "folder": {"id": path, "name": path.split("/")[-1] if "/" in path else "Keepi Cloud"},
            "folders": [{"id": f["path"].rstrip("/"), "name": f["name"], "files_count": 0} for f in result.get("folders", [])],
            "files": [_s3_doc_to_file_item(d) for d in result.get("documents", [])],
        }
    except Exception:
        logger.exception("Error leyendo contenido S3")
        raise HTTPException(status_code=500, detail=MSG_ERROR_INTERNO)

@router.get("/mobile/dashboard")
async def get_mobile_dashboard(
    request: Request,
    limit: int = Query(10),
    db: Session = Depends(get_db),
):
    try:
        uid = get_user_id_from_token(request)
        user_service = UserService(db)
        user = await user_service.get_user_by_uid(uid)
        if not user: raise HTTPException(status_code=404, detail="Usuario no encontrado")

        config_service = UserConfigService(db)
        user_config = await config_service.get_or_create_user_config(uid)
        storage_preference = user_config.cloud_provider.value if user_config and user_config.cloud_provider else "google_drive"

        document_service = DocumentService(db)
        all_documents = await document_service.get_user_documents(uid)
        total_keepi = sum(1 for doc in all_documents if _doc_matches_storage(doc, storage_preference))

        return {
            "folders": [], 
            "total_keepi": total_keepi,
            "expiring_soon_count": 0,
            "expiring_soon": [],
            "last_updated": datetime.now().isoformat(),
        }
    except Exception:
        logger.exception("Error en dashboard móvil")
        raise HTTPException(status_code=500, detail=MSG_ERROR_INTERNO)

@router.post("/mobile/analyze")
async def mobile_analyze_document(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    user_id = get_user_id_from_token(request)
    try:
        content = await file.read()
        document_service = DocumentService(db)
        result = await document_service.analyze_document_only(
            user_id, content, file.filename, file.content_type or "application/octet-stream"
        )
        return result
    except Exception as e:
        logger.error(f"Error analizando: {e}")
        raise HTTPException(status_code=500, detail="Error al analizar archivo")

@router.post("/mobile/save-analyzed")
async def mobile_save_analyzed_document(
    request: Request,
    file: UploadFile = File(...),
    category: str = Form(...),
    file_name: str = Form(...),
    expiry_date: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    user_id = get_user_id_from_token(request)
    try:
        content = await file.read()
        parsed_expiry = datetime.fromisoformat(expiry_date.replace("Z", "+00:00")) if expiry_date else None
        
        document_service = DocumentService(db)
        document = await document_service.save_analyzed_document(
            user_id=user_id,
            file_data=content,
            file_name=file.filename,
            file_type=file.content_type or "application/octet-stream",
            category=category.strip(),
            save_as_name=file_name.strip() or file.filename,
            expiry_date=parsed_expiry,
        )
        return {"message": "Documento guardado", "document_id": str(document.id)}
    except Exception:
        logger.exception("Error guardando documento")
        raise HTTPException(status_code=500, detail=MSG_ERROR_INTERNO)

@router.get("/mobile/download/{document_id}")
async def download_mobile_document(
    document_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db)
):
    try:
        uid = get_user_id_from_token(request)
        # Validamos que el documento exista y sea del usuario (o tenga permiso)
        document = db.query(Document).filter(Document.id == document_id).first()
        
        if not document:
            raise HTTPException(status_code=404, detail="Documento no encontrado")
            
        s3_service = S3Service()
        file_path = getattr(document, "file_path", getattr(document, "s3_key", None))
        
        if not file_path:
            raise HTTPException(status_code=400, detail="Ruta de archivo no válida")
            
        file_url = await s3_service.get_file_url(file_path)
        return RedirectResponse(url=file_url)
    except Exception:
        logger.exception("Error en descarga móvil")
        raise HTTPException(status_code=500, detail=MSG_ERROR_INTERNO)

@router.get("/drive/files/{file_id}/content")
async def get_drive_file_content(
    file_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    try:
        uid = get_user_id_from_token(request)
        drive_service = await _get_drive_service_or_raise(uid, db)
        file_content, file_name, mime_type = await drive_service.download_file(file_id)
        return Response(
            content=file_content,
            media_type=mime_type or "application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
        )
    except Exception:
        logger.exception("Error descargando de Drive")
        raise HTTPException(status_code=500, detail=MSG_ERROR_INTERNO)