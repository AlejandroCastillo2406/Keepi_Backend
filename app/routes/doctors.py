from uuid import UUID
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dto.clinical_intake_dto import ClinicalIntakeDetailResponse
from app.dto.timeline_dto import PriorDocumentItemResponse, TimelineEventResponse
from app.core.roles import ROLE_DOCTOR, ROLE_PATIENT
from app.core.security import require_no_temp_password_user
from app.models.doctor_timeline_note import (
    DoctorTimelineNoteCreate,
    DoctorTimelineNoteResponse,
)
from app.models.user import (
    DoctorCreatePatientRequest,
    DoctorCreatePatientResponse,
    User,
)
from app.models.appointment import AppointmentDoctorProposeRequest, AppointmentResponse
from app.factories.medical_factory import get_patient_timeline_service
from app.factories.user_factory import get_user_service
from app.services.medical.appointment_service import AppointmentService
from app.services.medical.patient_timeline_service import PatientTimelineService
from app.services.usuarios import UserService

router = APIRouter()


@router.post("/patients", response_model=DoctorCreatePatientResponse)
async def create_patient_account(
    body: DoctorCreatePatientRequest,
    current_user: User = Depends(require_no_temp_password_user),
    svc: UserService = Depends(get_user_service),
    db: Session = Depends(get_db),
):
    if current_user.role is None or current_user.role.name != ROLE_DOCTOR:
        raise HTTPException(status_code=403, detail="Solo usuarios con rol DOCTOR.")
    try:
        patient, plain_password = await svc.create_patient_by_doctor(
            current_user,
            body.email.strip(),
            body.name.strip(),
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    from app.services.medical.doctor_availability_service import (
        DoctorAvailabilityService,
    )
    from app.services.notificaciones.patient_invite_email_service import (
        build_public_scheduling_link,
        send_patient_invite_email,
    )

    raw_token = DoctorAvailabilityService.create_patient_scheduling_token(
        db, patient.id, current_user.id
    )
    scheduling_link = build_public_scheduling_link(raw_token)
    email_result = send_patient_invite_email(
        to_email=patient.email,
        patient_name=patient.name or "",
        temporary_password=plain_password,
        doctor_name=current_user.name,
        scheduling_link=scheduling_link,
    )

    message = "Paciente creado correctamente."
    if not email_result.success:
        message = (
            "Paciente creado, pero no se pudo enviar el correo de bienvenida. "
            f"{email_result.error or ''}".strip()
        )

    return DoctorCreatePatientResponse(
        id=str(patient.id),
        email=patient.email,
        name=patient.name,
        message=message,
        email_sent=email_result.success,
        email_error=email_result.error,
    )


@router.get("/patients")
async def list_my_patients(
    current_user: User = Depends(require_no_temp_password_user),
    svc: UserService = Depends(get_user_service),
):
    patient_role_id = svc.role_id_by_name(ROLE_PATIENT)
    rows = svc.list_patients_created_by_doctor(current_user.id, patient_role_id)
    return [{"id": str(u.id), "email": u.email, "name": u.name} for u in rows]


@router.post(
    "/appointments/{appointment_id}/propose-time", response_model=AppointmentResponse
)
async def propose_appointment_time(
    appointment_id: str,
    body: AppointmentDoctorProposeRequest,
    current_user: User = Depends(require_no_temp_password_user),
    db: Session = Depends(get_db),
):
    if current_user.role is None or current_user.role.name != ROLE_DOCTOR:
        raise HTTPException(status_code=403, detail="Solo usuarios con rol DOCTOR.")

    return AppointmentService.propose_doctor_time(
        db, appointment_id, str(current_user.id), body
    )


@router.get(
    "/patients/{patient_id}/timeline", response_model=List[TimelineEventResponse]
)
async def get_patient_timeline(
    patient_id: UUID,
    current_user: User = Depends(require_no_temp_password_user),
    timeline_svc: PatientTimelineService = Depends(get_patient_timeline_service),
):
    return timeline_svc.timeline_for_doctor_patient(current_user.id, patient_id)


@router.get(
    "/patients/{patient_id}/timeline/events/{event_id}/doctor-note",
    response_model=DoctorTimelineNoteResponse,
)
async def get_timeline_event_doctor_note(
    patient_id: UUID,
    event_id: str,
    current_user: User = Depends(require_no_temp_password_user),
    timeline_svc: PatientTimelineService = Depends(get_patient_timeline_service),
):
    return timeline_svc.get_doctor_note_for_event(
        current_user.id, patient_id, event_id
    )


@router.put(
    "/patients/{patient_id}/timeline/events/{event_id}/doctor-note",
    response_model=DoctorTimelineNoteResponse,
)
async def upsert_timeline_event_doctor_note(
    patient_id: UUID,
    event_id: str,
    payload: DoctorTimelineNoteCreate,
    current_user: User = Depends(require_no_temp_password_user),
    timeline_svc: PatientTimelineService = Depends(get_patient_timeline_service),
):
    event_type = (payload.event_type or "").strip()
    if not event_type:
        event_type = event_id.split("_", 1)[0] if "_" in event_id else "event"
    return timeline_svc.upsert_doctor_note_for_event(
        current_user.id,
        patient_id,
        event_id,
        event_type=event_type,
        content=payload.doctor_note,
    )


@router.get(
    "/patients/{patient_id}/prior-documents",
    response_model=List[PriorDocumentItemResponse],
)
async def list_patient_prior_documents(
    patient_id: UUID,
    current_user: User = Depends(require_no_temp_password_user),
    timeline_svc: PatientTimelineService = Depends(get_patient_timeline_service),
):
    return timeline_svc.prior_documents_for_doctor_patient(current_user.id, patient_id)


@router.get(
    "/patients/{patient_id}/clinical-intake/{invitation_id}",
    response_model=ClinicalIntakeDetailResponse,
)
async def get_patient_clinical_intake_detail(
    patient_id: UUID,
    invitation_id: UUID,
    current_user: User = Depends(require_no_temp_password_user),
    timeline_svc: PatientTimelineService = Depends(get_patient_timeline_service),
):
    return timeline_svc.clinical_intake_detail_for_doctor_patient(
        current_user.id, patient_id, invitation_id
    )
