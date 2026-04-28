from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, UploadFile, status

from app.core.security import require_doctor_user, require_patient_user
from app.dto.analysis_request_dto import AnalysisRequestCreate, AnalysisRequestResponse
from app.factories.medical_factory import get_analysis_request_service
from app.models.user import User
from app.services.documento.analysis_request_service import AnalysisRequestService

router = APIRouter()


@router.post(
    "/", response_model=AnalysisRequestResponse, status_code=status.HTTP_201_CREATED
)
async def create_request(
    data: AnalysisRequestCreate,
    current_user: User = Depends(require_doctor_user),
    svc: AnalysisRequestService = Depends(get_analysis_request_service),
):
    return svc.create_request(current_user.id, data)


@router.get("/me", response_model=List[AnalysisRequestResponse])
async def get_my_requests(
    current_user: User = Depends(require_patient_user),
    svc: AnalysisRequestService = Depends(get_analysis_request_service),
):
    return svc.get_pending_for_patient(current_user.id)


@router.get("/patient/{patient_id}", response_model=List[AnalysisRequestResponse])
async def get_patient_requests_history(
    patient_id: UUID,
    svc: AnalysisRequestService = Depends(get_analysis_request_service),
):
    return svc.list_history_for_patient(patient_id)


@router.patch("/{request_id}/complete", status_code=status.HTTP_200_OK)
async def complete_analysis_with_document(
    request_id: UUID,
    current_user: User = Depends(require_patient_user),
    document_id: UUID = Query(
        ..., description="ID del documento creado tras la subida"
    ),
    svc: AnalysisRequestService = Depends(get_analysis_request_service),
):
    return svc.complete_with_existing_document(
        patient_id=current_user.id,
        request_id=request_id,
        document_id=document_id,
    )


@router.patch("/{request_id}/upload")
async def upload_analysis_and_complete(
    request_id: UUID,
    current_user: User = Depends(require_patient_user),
    file: UploadFile = File(...),
    svc: AnalysisRequestService = Depends(get_analysis_request_service),
):
    return await svc.upload_and_complete(
        patient_uid=str(current_user.id), request_id=request_id, file=file
    )
