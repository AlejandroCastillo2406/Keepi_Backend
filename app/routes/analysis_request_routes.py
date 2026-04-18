from fastapi import APIRouter, Depends, HTTPException, status, Request, UploadFile, File
from sqlalchemy.orm import Session
from uuid import UUID
from typing import List
import base64
import json

# Importaciones de tu estructura real
from app.core.database import get_db
from app.dto.analysis_request_dto import AnalysisRequestCreate, AnalysisRequestResponse
from app.repositories.analysis_request_repository import AnalysisRequestRepository
from app.models.document import Document
from app.services.almacenamiento import S3Service, GoogleDriveService
from app.services.usuarios import UserConfigService

router = APIRouter()

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
    patient_id = get_user_id_from_token(request)
    repo = AnalysisRequestRepository(db)
    return repo.get_pending_by_patient(patient_id)

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
        
        if cloud_provider == "google_drive":
            # (Aquí iría tu lógica real de auth_refresh para Drive)
            drive_service = GoogleDriveService(...) 
            drive_file_id = await drive_service.upload_file(content, filename, mime_type)
        else: # assume keepi_cloud (S3)
            s3_service = S3Service()
            s3_key = await s3_service.upload_file(uid, content, filename, mime_type)
            
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