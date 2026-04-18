from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID
from typing import List

# Importaciones de tu estructura real
from app.core.database import get_db
from app.dto.analysis_request_dto import AnalysisRequestCreate, AnalysisRequestResponse
from app.repositories.analysis_request_repository import AnalysisRequestRepository

# ¡DESCOMENTAMOS ESTO! Es la pieza clave. 
# Esto lee el token de Flutter y sabe exactamente quién inició sesión.
from app.auth.auth_handler import get_current_user 

router = APIRouter()

# 1. DOCTOR: Crear una nueva solicitud
@router.post("/", response_model=AnalysisRequestResponse, status_code=status.HTTP_201_CREATED)
async def create_request(
    data: AnalysisRequestCreate, 
    db: Session = Depends(get_db),
    current_user: any = Depends(get_current_user) # <--- Ahora sabemos quién es el doctor
):
    repo = AnalysisRequestRepository(db)
    
    # EL GRAN ARREGLO: 
    # El doctor es el usuario logueado (current_user.id)
    # El paciente es el que seleccionaste en la app (data.patient_id)
    return repo.create(
        doctor_id=current_user.id,
        patient_id=data.patient_id,
        description=data.description
    )

# 2. PACIENTE: Obtener mis solicitudes pendientes
@router.get("/me", response_model=List[AnalysisRequestResponse])
async def get_my_requests(
    db: Session = Depends(get_db),
    current_user: any = Depends(get_current_user) # <--- Ahora sabemos quién es el paciente
):
    repo = AnalysisRequestRepository(db)
    
    # Buscamos en la base de datos solo las solicitudes de este paciente exacto
    return repo.get_pending_by_patient(current_user.id)

# 3. PACIENTE: Marcar solicitud como completada
@router.patch("/{request_id}/complete", response_model=AnalysisRequestResponse)
async def complete_request(
    request_id: UUID, 
    document_id: UUID, 
    db: Session = Depends(get_db),
    current_user: any = Depends(get_current_user) # Protegemos la ruta
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
    db: Session = Depends(get_db),
    current_user: any = Depends(get_current_user) # Protegemos la ruta
):
    repo = AnalysisRequestRepository(db)
    return repo.get_all_by_patient(patient_id)