import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, TypedDict

from jose import jwt
from pydantic import BaseModel, Field
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_no_temp_password_token
from app.exceptions import DriveAuthRequiredException
from app.factories.document_factory import (
    get_document_api_service,
    get_document_service,
)
from app.services.documento.document_api_service import (
    DocumentApiService,
    decode_uid_from_request_safe,
)
from app.services.documento import DocumentService
from app.models.document import Document, DocumentStatus, DocumentResponse

logger = logging.getLogger(__name__)
router = APIRouter()

MSG_ERROR_INTERNO = "Error interno del servidor"


class TokenPayload(TypedDict, total=False):
    uid: str
    email: Optional[str]
    name: Optional[str]


class MobileDocumentMetadataUpdate(BaseModel):
    name: Optional[str] = None
    file_name: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    expiry_date: Optional[datetime] = Field(
        None, description="Fecha de vencimiento ISO-8601"
    )
    document_number: Optional[str] = None
    organization: Optional[str] = None


class PatientLinkRequest(BaseModel):
    patient_name: str
    patient_email: Optional[str] = None


# ==========================================
# ENDPOINTS DE INVITACIÓN A PACIENTES
# ==========================================

@router.post("/generate-patient-link")
async def generate_patient_upload_link(
    body: PatientLinkRequest,
    user_token: TokenPayload = Depends(require_no_temp_password_token)
):
    """
    Genera un link temporal (24h) para que el paciente suba su expediente
    sin necesidad de iniciar sesión.
    """
    doctor_id = user_token["uid"]
    
    # Llave secreta (Asegúrate de tener SECRET_KEY en tu archivo .env)
    SECRET_KEY = os.getenv("SECRET_KEY", "keepi_super_secret_key_123")
    
    # Crear el contenido del token (Caduca en 24 horas)
    expire = datetime.now(timezone.utc) + timedelta(hours=24)
    payload = {
        "type": "patient_upload_pass",
        "doctor_id": doctor_id,
        "patient_name": body.patient_name,
        "exp": expire
    }
    
    # Firmar el token
    token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
    
    # Construir el link para tu Frontend
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000") 
    link = f"{frontend_url}/patient/upload?token={token}"
    
    return {
        "message": "Link temporal generado con éxito",
        "patient_name": body.patient_name,
        "link": link,
        "expires_at": expire
    }


# ==========================================
# ENDPOINTS DE VALIDACIÓN (Human-in-the-loop)
# ==========================================

@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document_details(
    document_id: uuid.UUID,
    user_token: TokenPayload = Depends(require_no_temp_password_token),
    db: Session = Depends(get_db)
):
    """
    Obtiene los detalles del documento para revisión médica.
    """
    doc = db.query(Document).filter(
        Document.id == document_id, 
        Document.user_id == user_token["uid"]
    ).first()
    
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
        
    return DocumentResponse.from_orm(doc)


@router.patch("/{document_id}/status", response_model=DocumentResponse)
async def update_document_status(
    document_id: uuid.UUID,
    status: DocumentStatus,
    user_token: TokenPayload = Depends(require_no_temp_password_token),
    db: Session = Depends(get_db)
):
    """
    Actualiza el estado del documento (PENDING_REVIEW, APPROVED, REJECTED).
    """
    doc = db.query(Document).filter(
        Document.id == document_id, 
        Document.user_id == user_token["uid"]
    ).first()
    
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    doc.status = status.value
    db.commit()
    db.refresh(doc)
    return DocumentResponse.from_orm(doc)


# ==========================================
# ENDPOINTS EXISTENTES
# ==========================================

@router.get("/s3/folders/contents")
async def get_s3_folder_contents(
    path: str = Query(
        ..., description="Ruta de carpeta S3 (ej. users/{uid}/Documentos personales)"
    ),
    user_token: TokenPayload = Depends(require_no_temp_password_token),
    api: DocumentApiService = Depends(get_document_api_service),
):
    try:
        uid = user_token["uid"]
        return await api.get_s3_folder_contents(uid, path)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error leyendo contenido S3")
        raise HTTPException(status_code=500, detail=MSG_ERROR_INTERNO)


@router.get("/keepi-cloud/root")
async def get_keepi_cloud_root(
    user_token: TokenPayload = Depends(require_no_temp_password_token),
    api: DocumentApiService = Depends(get_document_api_service),
):
    try:
        return await api.get_keepi_cloud_root(user_token["uid"])
    except Exception:
        logger.exception("Error leyendo Keepi Cloud root")
        raise HTTPException(status_code=500, detail=MSG_ERROR_INTERNO)


@router.get("/drive/folders/{folder_id}/contents")
async def get_drive_folder_contents(
    folder_id: str,
    user_token: TokenPayload = Depends(require_no_temp_password_token),
    api: DocumentApiService = Depends(get_document_api_service),
):
    try:
        return await api.get_drive_folder_contents(user_token["uid"], folder_id)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error listando contenido Drive")
        raise HTTPException(status_code=500, detail=MSG_ERROR_INTERNO)


@router.get("/s3/files/view-url")
async def get_s3_file_view_url(
    path: str = Query(..., description="Ruta S3 del archivo (users/{uid}/...)"),
    user_token: TokenPayload = Depends(require_no_temp_password_token),
    api: DocumentApiService = Depends(get_document_api_service),
):
    try:
        return await api.get_s3_file_view_url(user_token["uid"], path)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error obteniendo URL de vista S3")
        raise HTTPException(status_code=500, detail=MSG_ERROR_INTERNO)


@router.get("/s3/files/content")
async def get_s3_file_content(
    path: str = Query(..., description="Ruta S3 del archivo (users/{uid}/...)"),
    user_token: TokenPayload = Depends(require_no_temp_password_token),
    api: DocumentApiService = Depends(get_document_api_service),
):
    try:
        return await api.get_s3_file_content_response(user_token["uid"], path)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error descargando archivo S3")
        raise HTTPException(status_code=500, detail=MSG_ERROR_INTERNO)


@router.get("/drive/files/{file_id}/view-url")
async def get_drive_file_view_url(
    file_id: str,
    user_token: TokenPayload = Depends(require_no_temp_password_token),
    api: DocumentApiService = Depends(get_document_api_service),
):
    try:
        return await api.get_drive_file_view_url(user_token["uid"], file_id)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error obteniendo URL de vista Drive")
        raise HTTPException(status_code=500, detail=MSG_ERROR_INTERNO)


@router.get("/drive/files/{file_id}/content")
async def get_drive_file_content(
    file_id: str,
    user_token: TokenPayload = Depends(require_no_temp_password_token),
    api: DocumentApiService = Depends(get_document_api_service),
):
    try:
        return await api.get_drive_file_content_response(user_token["uid"], file_id)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error descargando archivo Drive")
        raise HTTPException(status_code=500, detail=MSG_ERROR_INTERNO)


@router.delete("/drive/files/{file_id}")
async def delete_drive_file(
    file_id: str,
    user_token: TokenPayload = Depends(require_no_temp_password_token),
    api: DocumentApiService = Depends(get_document_api_service),
):
    try:
        return await api.delete_drive_file(user_token["uid"], file_id)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error eliminando archivo Drive")
        raise HTTPException(status_code=500, detail=MSG_ERROR_INTERNO)


@router.get("/mobile/dashboard")
async def get_mobile_dashboard(
    user_token: TokenPayload = Depends(require_no_temp_password_token),
    limit: int = Query(10, description="Número de documentos a mostrar"),
    api: DocumentApiService = Depends(get_document_api_service),
):
    try:
        return await api.get_mobile_dashboard(user_token["uid"], limit)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error en mobile dashboard")
        raise HTTPException(status_code=500, detail=MSG_ERROR_INTERNO)


@router.post("/mobile/analyze")
async def mobile_analyze_document(
    file: UploadFile = File(...),
    user_token: TokenPayload = Depends(require_no_temp_password_token),
    document_service: DocumentService = Depends(get_document_service),
):
    user_id = user_token.get("uid", "unknown")
    logger.info(
        "[mobile/analyze] Solicitud recibida: usuario=%s, archivo=%s",
        user_id,
        file.filename,
    )
    try:
        if not file.filename:
            raise HTTPException(status_code=400, detail="Nombre de archivo requerido")
        content = await file.read()
        result = await document_service.analyze_document_only(
            user_token["uid"],
            content,
            file.filename,
            file.content_type or "application/octet-stream",
        )
        if result.get("subscription_required"):
            return JSONResponse(status_code=402, content=result)
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
    replaces_document_id: Optional[str] = Form(
        None, description="UUID del documento vencido/por vencer que se reemplaza"
    ),
    user_token: TokenPayload = Depends(require_no_temp_password_token),
    document_service: DocumentService = Depends(get_document_service),
):
    try:
        if not file.filename:
            raise HTTPException(status_code=400, detail="Nombre de archivo requerido")
        content = await file.read()
        parsed_expiry = None
        if expiry_date:
            try:
                parsed_expiry = datetime.fromisoformat(
                    expiry_date.replace("Z", "+00:00")
                )
            except ValueError:
                pass
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
            replaces_document_id=replaces_document_id,
        )
        msg = (
            "Documento reemplazado. El anterior quedó marcado como reemplazado."
            if replaces_document_id
            else "Documento guardado correctamente"
        )
        return {
            "message": msg,
            "document_id": str(document.id),
            "category": document.category,
            "file_name": document.file_name,
            "replaced_document_id": replaces_document_id,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        if isinstance(e, DriveAuthRequiredException):
            raise HTTPException(
                status_code=401,
                detail={"requires_drive_auth": True, "message": str(e)},
            )
        logger.exception("Error guardando documento analizado")
        raise HTTPException(status_code=500, detail=MSG_ERROR_INTERNO)


@router.post("/mobile/patient-upload")
async def upload_patient_document_direct(
    request: Request,
    file: UploadFile = File(...),
    document_service: DocumentService = Depends(get_document_service),
):
    uid = decode_uid_from_request_safe(request)
    try:
        content = await file.read()
        filename = file.filename or "estudio_medico.pdf"
        mime_type = file.content_type or "application/octet-stream"
        document = await document_service.upload_patient_clinical_study(
            uid,
            filename=filename,
            mime_type=mime_type,
            content=content,
        )
        cloud_provider = getattr(document, "cloud_provider", "") or ""
        return {
            "message": "Archivo subido exitosamente a " + str(cloud_provider),
            "document_id": str(document.id),
        }
    except ValueError as e:
        msg = str(e)
        if msg.startswith("DRIVE_AUTH|"):
            parts = msg.split("|", 2)
            url = parts[1] if len(parts) > 1 else ""
            detail = parts[2] if len(parts) > 2 else "Google Drive no autorizado"
            raise HTTPException(
                status_code=401,
                detail=detail,
                headers={"X-Drive-Auth-URL": url},
            )
        if msg == "GOOGLE_UNAUTHORIZED":
            raise HTTPException(status_code=401, detail="Google Drive no autorizado")
        raise HTTPException(status_code=400, detail=msg)
    except Exception:
        logger.exception("Error en subida directa del paciente")
        raise HTTPException(status_code=500, detail=MSG_ERROR_INTERNO)


@router.get("/mobile/{document_id}/metadata")
async def get_mobile_document_metadata(
    document_id: uuid.UUID,
    user_token: TokenPayload = Depends(require_no_temp_password_token),
    api: DocumentApiService = Depends(get_document_api_service),
):
    try:
        return await api.get_mobile_document_metadata(
            user_token["uid"], document_id
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error obteniendo metadatos del documento")
        raise HTTPException(status_code=500, detail=MSG_ERROR_INTERNO)


@router.patch("/mobile/{document_id}/metadata")
async def update_mobile_document_metadata(
    document_id: uuid.UUID,
    body: MobileDocumentMetadataUpdate,
    user_token: TokenPayload = Depends(require_no_temp_password_token),
    api: DocumentApiService = Depends(get_document_api_service),
):
    try:
        parsed_expiry = body.expiry_date
        if parsed_expiry is not None and parsed_expiry.tzinfo is None:
            parsed_expiry = parsed_expiry.replace(tzinfo=timezone.utc)
        return await api.update_mobile_document_metadata(
            user_token["uid"],
            document_id,
            name=body.name,
            file_name=body.file_name,
            category=body.category,
            description=body.description,
            expiry_date=parsed_expiry,
            document_number=body.document_number,
            organization=body.organization,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error actualizando metadatos del documento")
        raise HTTPException(status_code=500, detail=MSG_ERROR_INTERNO)


@router.get("/mobile/download/{document_id}")
async def download_mobile_document_direct(
    document_id: uuid.UUID,
    request: Request,
    api: DocumentApiService = Depends(get_document_api_service),
):
    decode_uid_from_request_safe(request)
    try:
        return await api.download_mobile_document(document_id)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error descargando archivo para el doctor")
        raise HTTPException(status_code=500, detail=MSG_ERROR_INTERNO)