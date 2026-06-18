from uuid import UUID
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dto.clinical_intake_dto import ClinicalIntakeDetailResponse
from app.dto.consultation_bootstrap_dto import ConsultationBootstrapResponse
from app.dto.patient_profile_bootstrap_dto import PatientProfileBootstrapResponse
from app.dto.consultation_context_dto import (
    ClinicalProfileUpdateRequest,
    ConsultationContextResponse,
)
from app.dto.timeline_dto import PriorDocumentItemResponse, TimelineEventResponse
from app.core.roles import ROLE_DOCTOR, ROLE_PATIENT
from app.core.security import require_no_temp_password_user
from app.models.doctor_timeline_note import (
    DoctorTimelineNoteCreate,
    DoctorTimelineNoteResponse,
)
from app.models.doctor_scheduling import PatientSchedulingLinkResponse
from app.models.user import (
    DoctorCreatePatientRequest,
    DoctorCreatePatientResponse,
    User,
)
from app.models.appointment import AppointmentDoctorProposeRequest, AppointmentResponse
from app.factories.medical_factory import get_patient_timeline_service
from app.factories.user_factory import get_user_service
from app.services.medical.appointment_service import AppointmentService
from app.services.medical.doctor_availability_service import DoctorAvailabilityService
from app.services.medical.consultation_bootstrap_service import (
    ConsultationBootstrapService,
)
from app.services.medical.patient_profile_bootstrap_service import (
    PatientProfileBootstrapService,
)
from app.services.medical.consultation_context_service import (
    ConsultationContextService,
)
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
        patient, _ = await svc.create_patient_by_doctor(
            current_user,
            body.email.strip(),
            body.name.strip(),
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    DoctorAvailabilityService.create_patient_scheduling_token(
        db, patient.id, current_user.id
    )

    # Correo de bienvenida con contraseña temporal y link de agenda: deshabilitado.
    return DoctorCreatePatientResponse(
        id=str(patient.id),
        email=patient.email,
        name=patient.name,
        message="Paciente creado correctamente.",
        email_sent=False,
        email_error=None,
    )


@router.get("/patients")
async def list_my_patients(
    current_user: User = Depends(require_no_temp_password_user),
    svc: UserService = Depends(get_user_service),
):
    patient_role_id = svc.role_id_by_name(ROLE_PATIENT)
    rows = svc.list_patients_created_by_doctor(current_user.id, patient_role_id)
    return [{"id": str(u.id), "email": u.email, "name": u.name} for u in rows]


@router.delete("/patients/{patient_id}", status_code=204)
async def delete_patient_account(
    patient_id: UUID,
    current_user: User = Depends(require_no_temp_password_user),
    svc: UserService = Depends(get_user_service),
):
    if current_user.role is None or current_user.role.name != ROLE_DOCTOR:
        raise HTTPException(status_code=403, detail="Solo usuarios con rol DOCTOR.")
    try:
        await svc.delete_patient_by_doctor(current_user, patient_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


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
    "/patients/{patient_id}/consultation-context",
    response_model=ConsultationContextResponse,
)
async def get_patient_consultation_context(
    patient_id: UUID,
    current_user: User = Depends(require_no_temp_password_user),
    db: Session = Depends(get_db),
):
    if current_user.role is None or current_user.role.name != ROLE_DOCTOR:
        raise HTTPException(status_code=403, detail="Solo usuarios con rol DOCTOR.")
    return ConsultationContextService(db).get_context(current_user.id, patient_id)


@router.get(
    "/patients/{patient_id}/appointments",
    response_model=List[AppointmentResponse],
)
async def list_patient_appointments_for_doctor(
    patient_id: UUID,
    current_user: User = Depends(require_no_temp_password_user),
    db: Session = Depends(get_db),
):
    if current_user.role is None or current_user.role.name != ROLE_DOCTOR:
        raise HTTPException(status_code=403, detail="Solo usuarios con rol DOCTOR.")
    rows = AppointmentService.list_doctor_patient_appointments(
        db, current_user.id, patient_id
    )
    return [AppointmentResponse.from_entity(r) for r in rows]


@router.get(
    "/patients/{patient_id}/profile-bootstrap",
    response_model=PatientProfileBootstrapResponse,
)
async def get_patient_profile_bootstrap(
    patient_id: UUID,
    current_user: User = Depends(require_no_temp_password_user),
    db: Session = Depends(get_db),
):
    if current_user.role is None or current_user.role.name != ROLE_DOCTOR:
        raise HTTPException(status_code=403, detail="Solo usuarios con rol DOCTOR.")
    return PatientProfileBootstrapService(db).get_bootstrap(
        current_user.id, patient_id
    )


@router.post(
    "/patients/{patient_id}/scheduling-link",
    response_model=PatientSchedulingLinkResponse,
)
async def generate_patient_scheduling_link(
    patient_id: UUID,
    current_user: User = Depends(require_no_temp_password_user),
    db: Session = Depends(get_db),
    user_svc: UserService = Depends(get_user_service),
):
    if current_user.role is None or current_user.role.name != ROLE_DOCTOR:
        raise HTTPException(status_code=403, detail="Solo usuarios con rol DOCTOR.")

    patient = user_svc.get_patient_if_owned_by_doctor(patient_id, current_user.id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Paciente no encontrado.")

    return DoctorAvailabilityService.build_patient_scheduling_link(
        db,
        current_user.id,
        patient_id,
        patient_name=patient.name or "",
    )


@router.get(
    "/patients/{patient_id}/consultation-bootstrap",
    response_model=ConsultationBootstrapResponse,
)
async def get_patient_consultation_bootstrap(
    patient_id: UUID,
    appointment_id: UUID = Query(...),
    current_user: User = Depends(require_no_temp_password_user),
    db: Session = Depends(get_db),
):
    if current_user.role is None or current_user.role.name != ROLE_DOCTOR:
        raise HTTPException(status_code=403, detail="Solo usuarios con rol DOCTOR.")
    return ConsultationBootstrapService(db).get_bootstrap(
        current_user.id, patient_id, appointment_id
    )


@router.put(
    "/patients/{patient_id}/clinical-profile",
    response_model=ConsultationContextResponse,
)
async def upsert_patient_clinical_profile(
    patient_id: UUID,
    body: ClinicalProfileUpdateRequest,
    current_user: User = Depends(require_no_temp_password_user),
    db: Session = Depends(get_db),
):
    if current_user.role is None or current_user.role.name != ROLE_DOCTOR:
        raise HTTPException(status_code=403, detail="Solo usuarios con rol DOCTOR.")
    return ConsultationContextService(db).upsert_profile(
        current_user.id, patient_id, body
    )


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
