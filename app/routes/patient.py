from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_patient_user
from app.dto.timeline_dto import PriorDocumentItemResponse, TimelineEventResponse
from app.models.appointment import (
    AppointmentPatientCreateRequest,
    AppointmentPatientRespondRequest,
    AppointmentResponse,
)
from app.models.user import User
from app.factories.medical_factory import get_patient_timeline_service
from app.services.medical.appointment_service import AppointmentService
from app.services.medical.patient_timeline_service import PatientTimelineService

router = APIRouter()


@router.post("/appointments/request", response_model=AppointmentResponse)
async def request_appointment(
    body: AppointmentPatientCreateRequest,
    patient: User = Depends(require_patient_user),
    db: Session = Depends(get_db),
):
    return AppointmentService.create_patient_request(db, str(patient.id), body)


@router.post(
    "/appointments/{appointment_id}/respond", response_model=AppointmentResponse
)
async def respond_to_appointment(
    appointment_id: str,
    body: AppointmentPatientRespondRequest,
    patient: User = Depends(require_patient_user),
    db: Session = Depends(get_db),
):
    return AppointmentService.respond_to_proposal(
        db, appointment_id, str(patient.id), body
    )


@router.get("/appointments", response_model=List[AppointmentResponse])
async def get_my_appointments(
    patient: User = Depends(require_patient_user),
    db: Session = Depends(get_db),
):
    return AppointmentService.get_appointments_by_patient(db, str(patient.id))


@router.get("/timeline", response_model=List[TimelineEventResponse])
async def get_my_care_timeline(
    patient: User = Depends(require_patient_user),
    timeline_svc: PatientTimelineService = Depends(get_patient_timeline_service),
):
    return timeline_svc.timeline_for_patient(str(patient.id))


@router.get("/prior-documents", response_model=List[PriorDocumentItemResponse])
async def get_my_prior_documents(
    patient: User = Depends(require_patient_user),
    timeline_svc: PatientTimelineService = Depends(get_patient_timeline_service),
):
    return timeline_svc.prior_documents_for_patient(str(patient.id))
