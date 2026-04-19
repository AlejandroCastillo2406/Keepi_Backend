import base64
import io
import json
import logging
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dto.analysis_request_dto import AnalysisRequestCreate, AnalysisRequestResponse
from app.models.document import Document
from app.repositories.analysis_request_repository import AnalysisRequestRepository
from app.services.almacenamiento import FolderService, GoogleDriveService, S3Service
from app.services.autenticacion import GoogleOAuthService
from app.services.usuarios import UserConfigService

router = APIRouter()
logger = logging.getLogger(__name__)
MSG_ERROR_INTERNO = "Error interno del servidor"

_ANALYSIS_DOCUMENT_CATEGORY = "Análisis Clínicos"

# --- FUNCIÓN DE UTILIDAD INTERNA (EVITA IMPORT CIRCULAR) ---
def get_user_id_from_token(request: Request) -> str:
    try:
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=401)
        token = auth_header.split(" ")[1]
        payload = json.loads(base64.b64decode(token.split(".")[1] + "==").decode("utf-8"))
        return payload.get("sub") or payload.get("id") or payload.get("uid")
    except:
        raise HTTPException(status_code=401, detail="Sesión inválida")

# --- ENDPOINTS ---

# 1. DOCTOR: Crear una nueva solicitud
@router.post("/", response_model=AnalysisRequestResponse, status_code=status.HTTP_201_CREATED)
async def create_request(
    data: AnalysisRequestCreate, 
    request: Request,
    db: Session = Depends(get_db)
):
    """Crea una solicitud de análisis vinculada al doctor que inició sesión."""
    doctor_id = get_user_id_from_token(request)
    repo = AnalysisRequestRepository(db)
    return repo.create(
        doctor_id=doctor_id,
        patient_id=data.patient_id,
        description=data.description
    )

# 2. PACIENTE: Obtener mis solicitudes pendientes
@router.get("/me", response_model=List[AnalysisRequestResponse])
async def get_my_requests(
    request: Request,
    db: Session = Depends(get_db)
):
    """Muestra todas las solicitudes que el paciente tiene pendientes por completar."""
    patient_raw = get_user_id_from_token(request)
    try:
        patient_uuid = patient_raw if isinstance(patient_raw, UUID) else UUID(str(patient_raw))
    except (ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Sesión inválida")
    repo = AnalysisRequestRepository(db)
    return repo.get_pending_by_patient(patient_uuid)

# 3. DOCTOR: Ver el historial completo de un paciente específico
@router.get("/patient/{patient_id}", response_model=List[AnalysisRequestResponse])
async def get_patient_requests_history(
    patient_id: UUID,
    db: Session = Depends(get_db)
):
    """Permite al doctor ver todas las solicitudes (pendientes y completadas) de un paciente."""
    repo = AnalysisRequestRepository(db)
    return repo.get_all_by_patient(patient_id)

# 4. EXCLUSIVO PACIENTE: Subir archivo, vincularlo y completar la solicitud
@router.patch("/{request_id}/upload")
async def upload_analysis_and_complete(
    request_id: UUID, 
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Este es EL endpoint:
    1. Sube el archivo a la nube configurada del paciente.
    2. Crea el Documento en la DB.
    3. Vincula el Documento a la Solicitud y cambia su estado a 'completed'.
    """
    uid = get_user_id_from_token(request)
    repo = AnalysisRequestRepository(db)
    
    # 1. Validar que la solicitud sea para ESTE paciente y esté pendiente
    analysis_req = repo.get_by_id(request_id)
    if not analysis_req or str(analysis_req.patient_id) != uid or analysis_req.status != "pending":
         raise HTTPException(status_code=404, detail="Solicitud no válida o ya completada.")
    
    try:
        content = await file.read()
        filename = file.filename or f"estudio_{request_id.hex}.{file.content_type.split('/')[-1]}"
        mime_type = file.content_type or "application/octet-stream"
        
        # 2. Determinar qué nube usar
        config_service = UserConfigService(db)
        user_config = await config_service.get_or_create_user_config(uid)
        
        # 3. Subir el archivo a la nube correspondiente
        cloud_provider = user_config.cloud_provider.value if user_config and user_config.cloud_provider else "google_drive"
        drive_file_id = None
        s3_key = None

        folder_service = FolderService(db)
        folder_result = await folder_service.ensure_category_folder_exists(
            uid, _ANALYSIS_DOCUMENT_CATEGORY, cloud_provider
        )
        if not folder_result.get("success"):
            if folder_result.get("requires_drive_auth"):
                raise HTTPException(
                    status_code=401,
                    detail=folder_result.get("error", "Google Drive no autorizado"),
                )
            raise HTTPException(
                status_code=400,
                detail=folder_result.get("error", "No se pudo preparar la carpeta de destino"),
            )

        if cloud_provider == "google_drive":
            oauth_service = GoogleOAuthService(db)
            credentials = await oauth_service.refresh_user_tokens(uid)
            if not credentials:
                raise HTTPException(status_code=401, detail="Google Drive no autorizado")
            drive_folder_id = folder_result.get("folder_id")
            if not drive_folder_id:
                raise HTTPException(status_code=500, detail="No se obtuvo carpeta en Google Drive")
            drive_service = GoogleDriveService(credentials)
            drive_file_id = await drive_service.upload_file(
                content, filename, drive_folder_id, mime_type
            )
        else:
            s3_service = S3Service()
            folder_name = folder_result.get("folder_name") or "other"
            upload_res = await s3_service.upload_document(
                uid,
                io.BytesIO(content),
                filename,
                mime_type,
                folder=folder_name,
            )
            s3_key = upload_res.get("file_path")
            
        # 4. Crear el Documento en la base de datos (tags para filtrar)
        document = Document(
            id=UUID(f"{uid[:8]}-{request_id.hex[8:12]}-4000-8000-{request_id.hex[16:28]}"), # Generar ID compuesto
            user_id=UUID(uid),
            cloud_provider=cloud_provider,
            drive_file_id=drive_file_id,
            s3_key=s3_key,
            filename=filename,
            type=mime_type.split("/")[0], # ej: image o application (pdf)
            tags={"analysis_request": str(request_id)},
            description=f"Archivo subido para solicitud: {analysis_req.description}"
        )
        db.add(document)
        db.commit()
        db.refresh(document)
        
        # 5. Completar la solicitud de análisis vinculando el documento
        updated_request = repo.mark_as_completed(request_id, document.id)
        
        return {
            "message": "Archivo subido y solicitud completada.",
            "request_id": str(updated_request.id),
            "document_id": str(document.id)
        }
        
    except Exception:
        db.rollback()
        logger.exception("Error en upload_analysis_and_complete")
        raise HTTPException(status_code=500, detail=MSG_ERROR_INTERNO)