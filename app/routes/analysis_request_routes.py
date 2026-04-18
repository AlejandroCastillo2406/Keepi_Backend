from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from uuid import UUID
from typing import List
import base64
import json

# Importaciones de tu estructura
from app.core.database import get_db
from app.dto.analysis_request_dto import AnalysisRequestCreate, AnalysisRequestResponse
from app.repositories.analysis_request_repository import AnalysisRequestRepository

router = APIRouter()

# --- FUNCIÓN DE UTILIDAD INTERNA ---
# Se define aquí mismo para evitar el error de "Importación Circular" en Render
def get_user_id_from_token(request: Request) -> str:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="No se envió el token de seguridad"
        )
    
    token = auth_header.split(" ")[1]
    try:
        # Decodificamos el payload del JWT (parte central)
        payload_part = token.split(".")[1]
        # Ajustamos el padding para que base64 no falle
        missing_padding = len(payload_part) % 4
        if missing_padding:
            payload_part += '=' * (4 - missing_padding)
            
        payload_json = base64.b64decode(payload_part).decode("utf-8")
        payload = json.loads(payload_json)
        
        # Buscamos el ID del usuario en las claves comunes de JWT
        user_id = payload.get("sub") or payload.get("id") or payload.get("uid")
        if not user_id:
            raise ValueError("ID de usuario no encontrado")
            
        return user_id
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Sesión inválida o expirada"
        )

# 1. DOCTOR: Crear una nueva solicitud
@router.post("/", response_model=AnalysisRequestResponse, status_code=status.HTTP_201_CREATED)
async def create_request(
    data: AnalysisRequestCreate, 
    request: Request,
    db: Session = Depends(get_db)
):
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
    patient_id = get_user_id_from_token(request)
    repo = AnalysisRequestRepository(db)
    return repo.get_pending_by_patient(patient_id)

# 3. PACIENTE: Marcar solicitud como completada (subida de archivo)
@router.patch("/{request_id}/complete", response_model=AnalysisRequestResponse)
async def complete_request(
    request_id: UUID, 
    document_id: UUID, 
    db: Session = Depends(get_db)
):
    repo = AnalysisRequestRepository(db)
    updated_request = repo.mark_as_completed(request_id, document_id)
    
    if not updated_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="La solicitud de análisis no existe"
        )
    return updated_request

# 4. DOCTOR: Ver el historial completo de un paciente específico
@router.get("/patient/{patient_id}", response_model=List[AnalysisRequestResponse])
async def get_patient_requests_history(
    patient_id: UUID,
    db: Session = Depends(get_db)
):
    repo = AnalysisRequestRepository(db)
    return repo.get_all_by_patient(patient_id)