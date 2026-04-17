from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID
from typing import List

# Importaciones ajustadas a tu estructura real
from app.core.database import get_db
from app.dto.analysis_request_dto import AnalysisRequestCreate, AnalysisRequestResponse
from app.repositories.analysis_request_repository import AnalysisRequestRepository

# COMENTAMOS ESTO PARA QUE NO DE ERROR SI NO TIENES EL ARCHIVO
# from app.auth.auth_handler import get_current_user 

router = APIRouter()

# 1. DOCTOR: Crear una nueva solicitud
@router.post("/", response_model=AnalysisRequestResponse, status_code=status.HTTP_201_CREATED)
async def create_request(
    data: AnalysisRequestCreate, 
    db: Session = Depends(get_db)
    # current_user: any = Depends(get_current_user) # <--- Comentado para evitar error
):
    repo = AnalysisRequestRepository(db)
    
    # IMPORTANTE: Como quitamos el 'current_user', aquí 
    # de momento usaremos un ID de prueba o el que tú definas.
    # En producción aquí debería ir el ID del doctor logueado.
    doctor_id_prueba = data.patient_id # Solo para que no falle al insertar
    
    return repo.create(
        doctor_id=doctor_id_prueba,
        patient_id=data.patient_id,
        description=data.description
    )

# 2. PACIENTE: Obtener mis solicitudes pendientes
@router.get("/me", response_model=List[AnalysisRequestResponse])
async def get_my_requests(
    patient_id: UUID, # Lo pedimos por ahora manualmente para probar
    db: Session = Depends(get_db)
):
    repo = AnalysisRequestRepository(db)
    return repo.get_pending_by_patient(patient_id)

# 3. PACIENTE: Marcar solicitud como completada
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

# 4. DOCTOR: Ver el historial de un paciente
@router.get("/patient/{patient_id}", response_model=List[AnalysisRequestResponse])
async def get_patient_requests_history(
    patient_id: UUID,
    db: Session = Depends(get_db)
):
    repo = AnalysisRequestRepository(db)
    return repo.get_all_by_patient(patient_id)