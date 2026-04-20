import base64
import io
import json
import logging
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dto.analysis_request_dto import AnalysisRequestCreate, AnalysisRequestResponse
from app.models.analysis_request import AnalysisRequest
from app.models.document import Document
from app.models.notification import NotificationType
from app.models.user import User
from app.repositories.analysis_request_repository import AnalysisRequestRepository
from app.services.notificaciones.user_notify import notify_user_push_and_db
from app.services.almacenamiento import FolderService, GoogleDriveService, S3Service
from app.services.autenticacion import GoogleOAuthService
from app.services.usuarios import UserConfigService

router = APIRouter()
logger = logging.getLogger(__name__)
MSG_ERROR_INTERNO = "Error interno del servidor"

_ANALYSIS_DOCUMENT_CATEGORY = "Análisis Clínicos"


def _truncate(text: str, max_len: int) -> str:
    t = (text or "").strip()
    if len(t) <= max_len:
        return t
    return t[: max_len - 3] + "..."


def _notify_patient_new_analysis_request(
    db: Session,
    *,
    patient_id: UUID,
    doctor_id: UUID,
    analysis_request_id: UUID,
    description: str,
) -> None:
    doctor = db.query(User).filter(User.id == doctor_id).first()
    doctor_name = (doctor.name if doctor else None) or "Tu médico"
    desc_preview = _truncate(description, 220)
    body = (
        f"{doctor_name} te pidió subir resultados: {desc_preview}"
        if desc_preview
        else f"{doctor_name} te envió una solicitud de análisis."
    )
    notify_user_push_and_db(
        db,
        patient_id,
        title="Nueva solicitud de análisis",
        message=body,
        notification_type=NotificationType.INFO,
        payload={
            "analysis_request_id": str(analysis_request_id),
            "doctor_id": str(doctor_id),
            "description": description,
        },
        push_data={
            "type": "analysis_request_assigned",
            "analysis_request_id": str(analysis_request_id),
            "doctor_id": str(doctor_id),
            "title": "Nueva solicitud de análisis",
            "body": body,
        },
    )


def _notify_doctor_analysis_completed(
    db: Session,
    *,
    analysis_req: AnalysisRequest,
    document_id: UUID,
) -> None:
    patient = db.query(User).filter(User.id == analysis_req.patient_id).first()
    patient_name = (patient.name if patient else None) or "Paciente"
    desc_preview = _truncate(analysis_req.description or "", 180)
    body = (
        f"{patient_name} completó la solicitud: {desc_preview}"
        if desc_preview
        else f"{patient_name} subió el estudio solicitado."
    )
    notify_user_push_and_db(
        db,
        analysis_req.doctor_id,
        title="Estudio completado",
        message=body,
        notification_type=NotificationType.INFO,
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
    doctor_raw = get_user_id_from_token(request)
    try:
        doctor_uuid = doctor_raw if isinstance(doctor_raw, UUID) else UUID(str(doctor_raw))
    except (ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Sesión inválida")
    repo = AnalysisRequestRepository(db)
    created = repo.create(
        doctor_id=doctor_uuid,
        patient_id=data.patient_id,
        description=data.description,
    )
    _notify_patient_new_analysis_request(
        db,
        patient_id=data.patient_id,
        doctor_id=doctor_uuid,
        analysis_request_id=created.id,
        description=data.description,
    )
    return created

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

# 4a. EXCLUSIVO PACIENTE: Vincular un documento ya subido y completar la solicitud (flujo móvil: upload + PATCH)
@router.patch("/{request_id}/complete", status_code=status.HTTP_200_OK)
async def complete_analysis_with_document(
    request_id: UUID,
    request: Request,
    document_id: UUID = Query(..., description="ID del documento creado tras la subida (ej. POST /documents/mobile/patient-upload)"),
    db: Session = Depends(get_db),
):
    """
    El paciente sube el archivo con `/documents/mobile/patient-upload` y luego llama aquí
    para marcar la solicitud como completada y asociar el `document_id`.
    """
    uid = get_user_id_from_token(request)
    try:
        patient_uuid = uid if isinstance(uid, UUID) else UUID(str(uid))
    except (ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Sesión inválida")

    repo = AnalysisRequestRepository(db)
    analysis_req = repo.get_by_id(request_id)
    if not analysis_req or analysis_req.patient_id != patient_uuid or analysis_req.status != "pending":
        raise HTTPException(status_code=404, detail="Solicitud no válida o ya completada.")

    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc or doc.user_id != patient_uuid:
        raise HTTPException(status_code=404, detail="Documento no encontrado o no pertenece al usuario.")

    updated = repo.mark_as_completed(request_id, document_id)
    if not updated:
        raise HTTPException(status_code=500, detail="No se pudo completar la solicitud.")

    _notify_doctor_analysis_completed(db, analysis_req=updated, document_id=document_id)

    return {
        "message": "Solicitud completada.",
        "request_id": str(request_id),
        "document_id": str(document_id),
    }


# 4b. EXCLUSIVO PACIENTE: Subir archivo en un solo paso (multipart) y completar
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
        file_url = None

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
            if drive_file_id:
                file_url = f"https://drive.google.com/file/d/{drive_file_id}/view"
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
            file_url = upload_res.get("signed_url")

        # 4. Crear el Documento en la base de datos (tags: ARRAY de strings en PostgreSQL)
        document = Document(
            user_id=UUID(uid),
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
        db.add(document)
        db.commit()
        db.refresh(document)
        
        # 5. Completar la solicitud de análisis vinculando el documento
        updated_request = repo.mark_as_completed(request_id, document.id)
        if not updated_request:
            raise HTTPException(status_code=500, detail="No se pudo completar la solicitud.")

        _notify_doctor_analysis_completed(db, analysis_req=updated_request, document_id=document.id)

        return {
            "message": "Archivo subido y solicitud completada.",
            "request_id": str(updated_request.id),
            "document_id": str(document.id)
        }
        
    except Exception:
        db.rollback()
        logger.exception("Error en upload_analysis_and_complete")
        raise HTTPException(status_code=500, detail=MSG_ERROR_INTERNO)