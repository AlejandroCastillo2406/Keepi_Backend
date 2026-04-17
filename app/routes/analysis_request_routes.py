from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID
from typing import List

# Importaciones de tu arquitectura
from app.config.database import get_db
from app.dto.analysis_request_dto import AnalysisRequestCreate, AnalysisRequestResponse
from app.repositories.analysis_request_repository import AnalysisRequestRepository
from app.auth.auth_handler import get_current_user # Ajusta según tu sistema de auth

router = APIRouter()

# 1. DOCTOR: Crear una nueva solicitud
@router.post("/analysis-requests", response_model=AnalysisRequestResponse, status_code=status.HTTP_201_CREATED)
async def create_request(
    data: AnalysisRequestCreate, 
    db: Session = Depends(get_db),
    current_user: any = Depends(get_current_user) # Aquí validarías que sea rol Doctor
):
    repo = AnalysisRequestRepository(db)
    # doctor_id viene del token de sesión (current_user)
    return repo.create(
        doctor_id=current_user.id,
        patient_id=data.patient_id,
        description=data.description
    )

# 2. PACIENTE: Obtener mis solicitudes pendientes
@router.get("/analysis-requests/me", response_model=List[AnalysisRequestResponse])
async def get_my_requests(
    db: Session = Depends(get_db),
    current_user: any = Depends(get_current_user) # Aquí validarías que sea rol Paciente
):
    repo = AnalysisRequestRepository(db)
    return repo.get_pending_by_patient(current_user.id)

# 3. PACIENTE: Marcar solicitud como completada (vincular con el documento)
@router.patch("/analysis-requests/{request_id}/complete", response_model=AnalysisRequestResponse)
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

# 4. DOCTOR: Ver el historial de solicitudes de un paciente específico
@router.get("/analysis-requests/patient/{patient_id}", response_model=List[AnalysisRequestResponse])
async def get_patient_requests_history(
    patient_id: UUID,
    db: Session = Depends(get_db),
    current_user: any = Depends(get_current_user)
):
    repo = AnalysisRequestRepository(db)
    # Aquí podrías validar que el doctor tenga permiso de ver a este paciente
    return repo.get_all_by_patient(patient_id)