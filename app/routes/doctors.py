"""Endpoints exclusivos del flujo médico (alta de pacientes, expedientes y gestión de citas)."""

from uuid import UUID
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.roles import ROLE_DOCTOR, ROLE_PATIENT
from app.core.security import require_no_temp_password_user
from app.models.patient_medical_record import MedicalRecordResponse
from app.models.health_questionnaire import (
    DoctorQuestionCreateRequest,
    DoctorQuestionListResponse,
    DoctorQuestionnaireSettingsPatchRequest,
    DoctorQuestionnaireSettingsResponse,
    DoctorQuestionOut,
    DoctorQuestionReorderRequest,
    DoctorQuestionUpdateRequest,
    SpecialtiesListResponse,
    TemplateAssignRequest,
    TemplateCreateRequest,
    TemplateDetailOut,
    TemplateListResponse,
    TemplateUpdateRequest,
)
from app.models.user import DoctorCreatePatientRequest, DoctorCreatePatientResponse, User
from app.models.user import User as UserModel
from app.models.appointment import Appointment 
from app.services.medical import MedicalRecordService
from app.services.health_questionnaire_service import (
    assign_template_to_patients,
    create_doctor_question,
    create_template,
    delete_doctor_question,
    delete_template,
    get_doctor_settings,
    get_template_detail,
    list_questions_for_doctor,
    list_specialties_for_doctor,
    list_templates,
    patch_doctor_settings,
    reorder_doctor_questions,
    toggle_question_active_for_doctor,
    unassign_template_from_patient,
    update_doctor_question,
    update_template,
)
from app.services.notificaciones.patient_invite_email_service import send_patient_invite_email
from app.services.usuarios import UserService

# IMPORTACIONES DEL TIMELINE
from app.repositories.patient_repository import PatientRepository
from app.dto.timeline_dto import TimelineEventResponse

router = APIRouter()
patient_repo = PatientRepository()

# ==========================================
# CUESTIONARIO DE SALUD (médico)
# - Rutas nuevas: /health-questionnaire/specialties, /questions, /templates
# - Legacy: /health-questionnaire/settings (+ alias /me/…) — solo on/off sobre preguntas de Keepi
# Todas van arriba del archivo para no chocar con /patients/{uuid}/...
# ==========================================


def _require_doctor(current_user: User) -> None:
    if current_user.role is None or current_user.role.name != ROLE_DOCTOR:
        raise HTTPException(status_code=403, detail="Solo usuarios con rol DOCTOR.")


# --- Especialidades y conteos ----------------------------------------------


@router.get("/health-questionnaire/specialties", response_model=SpecialtiesListResponse)
async def list_hq_specialties(
    current_user: User = Depends(require_no_temp_password_user),
    db: Session = Depends(get_db),
):
    _require_doctor(current_user)
    return list_specialties_for_doctor(db, current_user.id)


# --- Preguntas por especialidad / globales ---------------------------------


@router.get(
    "/health-questionnaire/specialties/{specialty_code}/questions",
    response_model=DoctorQuestionListResponse,
)
async def list_hq_questions_for_specialty(
    specialty_code: str,
    status: str = "all",
    q: Optional[str] = None,
    current_user: User = Depends(require_no_temp_password_user),
    db: Session = Depends(get_db),
):
    _require_doctor(current_user)
    return list_questions_for_doctor(
        db, current_user.id, specialty_code=specialty_code, status=status, search=q
    )


@router.get("/health-questionnaire/global-questions", response_model=DoctorQuestionListResponse)
async def list_hq_global_questions(
    status: str = "all",
    q: Optional[str] = None,
    current_user: User = Depends(require_no_temp_password_user),
    db: Session = Depends(get_db),
):
    _require_doctor(current_user)
    return list_questions_for_doctor(
        db, current_user.id, specialty_code=None, status=status, search=q
    )


@router.post("/health-questionnaire/questions", response_model=DoctorQuestionOut)
async def create_hq_question(
    body: DoctorQuestionCreateRequest,
    current_user: User = Depends(require_no_temp_password_user),
    db: Session = Depends(get_db),
):
    _require_doctor(current_user)
    try:
        return create_doctor_question(db, current_user, body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/health-questionnaire/questions/{question_id}", response_model=DoctorQuestionOut)
async def update_hq_question(
    question_id: UUID,
    body: DoctorQuestionUpdateRequest,
    current_user: User = Depends(require_no_temp_password_user),
    db: Session = Depends(get_db),
):
    _require_doctor(current_user)
    try:
        return update_doctor_question(db, current_user, question_id, body)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/health-questionnaire/questions/{question_id}")
async def delete_hq_question(
    question_id: UUID,
    current_user: User = Depends(require_no_temp_password_user),
    db: Session = Depends(get_db),
):
    _require_doctor(current_user)
    try:
        delete_doctor_question(db, current_user, question_id)
        return {"success": True}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch(
    "/health-questionnaire/questions/{question_id}/active",
    response_model=DoctorQuestionOut,
)
async def toggle_hq_question_active(
    question_id: UUID,
    is_active: bool,
    current_user: User = Depends(require_no_temp_password_user),
    db: Session = Depends(get_db),
):
    _require_doctor(current_user)
    try:
        return toggle_question_active_for_doctor(db, current_user, question_id, is_active)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/health-questionnaire/questions/reorder")
async def reorder_hq_questions(
    body: DoctorQuestionReorderRequest,
    current_user: User = Depends(require_no_temp_password_user),
    db: Session = Depends(get_db),
):
    _require_doctor(current_user)
    reorder_doctor_questions(db, current_user, body)
    return {"success": True}


# --- Plantillas personalizadas ---------------------------------------------


@router.get("/health-questionnaire/templates", response_model=TemplateListResponse)
async def list_hq_templates(
    current_user: User = Depends(require_no_temp_password_user),
    db: Session = Depends(get_db),
):
    _require_doctor(current_user)
    return list_templates(db, current_user)


@router.post("/health-questionnaire/templates", response_model=TemplateDetailOut)
async def create_hq_template(
    body: TemplateCreateRequest,
    current_user: User = Depends(require_no_temp_password_user),
    db: Session = Depends(get_db),
):
    _require_doctor(current_user)
    try:
        return create_template(db, current_user, body)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/health-questionnaire/templates/{template_id}", response_model=TemplateDetailOut)
async def get_hq_template(
    template_id: UUID,
    current_user: User = Depends(require_no_temp_password_user),
    db: Session = Depends(get_db),
):
    _require_doctor(current_user)
    try:
        return get_template_detail(db, current_user, template_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/health-questionnaire/templates/{template_id}", response_model=TemplateDetailOut)
async def update_hq_template(
    template_id: UUID,
    body: TemplateUpdateRequest,
    current_user: User = Depends(require_no_temp_password_user),
    db: Session = Depends(get_db),
):
    _require_doctor(current_user)
    try:
        return update_template(db, current_user, template_id, body)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/health-questionnaire/templates/{template_id}")
async def delete_hq_template(
    template_id: UUID,
    current_user: User = Depends(require_no_temp_password_user),
    db: Session = Depends(get_db),
):
    _require_doctor(current_user)
    try:
        delete_template(db, current_user, template_id)
        return {"success": True}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/health-questionnaire/templates/{template_id}/assignments",
    response_model=TemplateDetailOut,
)
async def assign_hq_template(
    template_id: UUID,
    body: TemplateAssignRequest,
    current_user: User = Depends(require_no_temp_password_user),
    db: Session = Depends(get_db),
):
    _require_doctor(current_user)
    try:
        return assign_template_to_patients(db, current_user, template_id, body)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete(
    "/health-questionnaire/templates/{template_id}/assignments/{patient_id}",
)
async def unassign_hq_template(
    template_id: UUID,
    patient_id: UUID,
    current_user: User = Depends(require_no_temp_password_user),
    db: Session = Depends(get_db),
):
    _require_doctor(current_user)
    try:
        unassign_template_from_patient(db, current_user, template_id, patient_id)
        return {"success": True}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# --- Legacy: ajustes antiguos (se conservan para no romper clientes viejos) ---


@router.get("/health-questionnaire/settings", response_model=DoctorQuestionnaireSettingsResponse)
@router.get(
    "/me/health-questionnaire/settings",
    response_model=DoctorQuestionnaireSettingsResponse,
    include_in_schema=False,
)
async def get_my_health_questionnaire_settings(
    current_user: User = Depends(require_no_temp_password_user),
    db: Session = Depends(get_db),
):
    _require_doctor(current_user)
    return get_doctor_settings(db, current_user)


@router.patch("/health-questionnaire/settings", response_model=DoctorQuestionnaireSettingsResponse)
@router.patch(
    "/me/health-questionnaire/settings",
    response_model=DoctorQuestionnaireSettingsResponse,
    include_in_schema=False,
)
async def patch_my_health_questionnaire_settings(
    body: DoctorQuestionnaireSettingsPatchRequest,
    current_user: User = Depends(require_no_temp_password_user),
    db: Session = Depends(get_db),
):
    _require_doctor(current_user)
    try:
        return patch_doctor_settings(db, current_user, body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ==========================================
# RUTAS DE PACIENTES
# ==========================================

@router.post("/patients", response_model=DoctorCreatePatientResponse)
async def create_patient_account(
    body: DoctorCreatePatientRequest,
    current_user: User = Depends(require_no_temp_password_user),
    db: Session = Depends(get_db),
):
    if current_user.role is None or current_user.role.name != ROLE_DOCTOR:
        raise HTTPException(status_code=403, detail="Solo usuarios con rol DOCTOR.")
    svc = UserService(db)
    try:
        patient, plain_password = await svc.create_patient_by_doctor(
            current_user, body.email.strip(), body.name.strip(), body.medical_record,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    send_patient_invite_email(patient.email, patient.name, plain_password)
    return DoctorCreatePatientResponse(id=str(patient.id), email=patient.email, name=patient.name)

@router.get("/patients")
async def list_my_patients(
    current_user: User = Depends(require_no_temp_password_user),
    db: Session = Depends(get_db),
):
    svc = UserService(db)
    patient_role_id = svc.role_id_by_name(ROLE_PATIENT)
    rows = db.query(UserModel).filter(
        UserModel.created_by_user_id == current_user.id,
        UserModel.role_id == patient_role_id
    ).order_by(UserModel.created_at.desc()).all()
    return [{"id": str(u.id), "email": u.email, "name": u.name} for u in rows]

# ==========================================
# RUTAS DE CITAS Y EXPEDIENTE
# ==========================================

@router.get("/patients/{patient_id}/medical-record", response_model=MedicalRecordResponse)
async def get_patient_medical_record(
    patient_id: UUID,
    current_user: User = Depends(require_no_temp_password_user),
    db: Session = Depends(get_db),
):
    svc = MedicalRecordService(db)
    return svc.get_response_for_doctor(current_user, patient_id)

# ==========================================
# RUTA DE LÍNEA DE TIEMPO
# ==========================================

@router.get("/patients/{patient_id}/timeline", response_model=List[TimelineEventResponse])
async def get_patient_timeline(
    patient_id: UUID,
    current_user: User = Depends(require_no_temp_password_user),
    db: Session = Depends(get_db),
):
    """Obtiene el historial completo de eventos del paciente."""
    # Validar pertenencia
    patient = db.query(UserModel).filter(
        UserModel.id == patient_id,
        UserModel.created_by_user_id == current_user.id
    ).first()

    if not patient:
        raise HTTPException(status_code=404, detail="Paciente no vinculado a su cuenta.")

    # Llamar al repositorio real
    return patient_repo.get_timeline_events(db, str(patient_id))