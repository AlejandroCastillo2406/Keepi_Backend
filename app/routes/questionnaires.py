"""Cuestionarios diagnósticos: configuración doctor, llenado paciente."""
from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_doctor_user, require_patient_user
from app.models.medical_specialty import MedicalSpecialty
from app.models.questionnaire_catalog import (
    DoctorQuestionnaireSettings,
    QuestionnaireAnswer,
    QuestionnaireResponse,
    DoctorQuestionnaireSettingsResponse,
    DoctorQuestionnaireSettingsUpdate,
    PublishCustomBody,
    QuestionnaireRequiredResponse,
)
from app.models.user import User
from app.services.notificaciones.user_notify import notify_user_push_and_db
from app.services.questionnaires.merge import (
    ensure_doctor_active_version,
    latest_published_for_slug,
    materialize_system_composed,
    specialty_slug_for_code,
)
from app.services.questionnaires.publish_custom import publish_custom_from_payload
from app.services.questionnaires.schema import version_title, version_to_questions

router = APIRouter()


class SpecialtyOut(BaseModel):
    id: str
    code: str
    name_es: str


class DoctorSpecialtyBody(BaseModel):
    specialty_id: str


class PatchAnswersBody(BaseModel):
    answers: dict[str, Any] = Field(default_factory=dict)


@router.get("/specialties", response_model=list[SpecialtyOut])
async def list_specialties(db: Session = Depends(get_db)):
    rows = db.query(MedicalSpecialty).order_by(MedicalSpecialty.name_es).all()
    return [SpecialtyOut(id=str(r.id), code=r.code, name_es=r.name_es) for r in rows]


@router.put("/doctors/me/specialty")
async def set_doctor_specialty(
    body: DoctorSpecialtyBody,
    current_user: User = Depends(require_doctor_user),
    db: Session = Depends(get_db),
):
    spec = db.query(MedicalSpecialty).filter(MedicalSpecialty.id == UUID(body.specialty_id)).first()
    if not spec:
        raise HTTPException(status_code=404, detail="Especialidad no encontrada.")
    current_user.specialty_id = spec.id
    db.commit()
    return {"ok": True, "specialty_id": str(spec.id), "code": spec.code}


@router.get("/me/settings", response_model=DoctorQuestionnaireSettingsResponse)
async def get_doctor_settings(
    current_user: User = Depends(require_doctor_user),
    db: Session = Depends(get_db),
):
    st = db.query(DoctorQuestionnaireSettings).filter(DoctorQuestionnaireSettings.doctor_id == current_user.id).first()
    spec_name = None
    spec_code = None
    if current_user.specialty_id:
        sp = db.query(MedicalSpecialty).filter(MedicalSpecialty.id == current_user.specialty_id).first()
        if sp:
            spec_name = sp.name_es
            spec_code = sp.code
    if not st:
        return DoctorQuestionnaireSettingsResponse(
            doctor_id=str(current_user.id),
            medical_specialty_id=str(current_user.specialty_id) if current_user.specialty_id else None,
            specialty_code=spec_code,
            specialty_name=spec_name,
            mode="system_composed",
            include_base_in_custom=True,
            active_version_id=None,
        )
    return DoctorQuestionnaireSettingsResponse(
        doctor_id=str(current_user.id),
        medical_specialty_id=str(st.medical_specialty_id) if st.medical_specialty_id else None,
        specialty_code=spec_code,
        specialty_name=spec_name,
        mode=st.mode,
        include_base_in_custom=st.include_base_in_custom,
        active_version_id=str(st.active_version_id) if st.active_version_id else None,
    )


@router.put("/me/settings")
async def put_doctor_settings(
    body: DoctorQuestionnaireSettingsUpdate,
    current_user: User = Depends(require_doctor_user),
    db: Session = Depends(get_db),
):
    if body.medical_specialty_id:
        spec = db.query(MedicalSpecialty).filter(MedicalSpecialty.id == UUID(body.medical_specialty_id)).first()
        if not spec:
            raise HTTPException(status_code=404, detail="Especialidad no encontrada.")
        current_user.specialty_id = spec.id

    st = db.query(DoctorQuestionnaireSettings).filter(DoctorQuestionnaireSettings.doctor_id == current_user.id).first()
    if not st:
        st = DoctorQuestionnaireSettings(
            doctor_id=current_user.id,
            medical_specialty_id=current_user.specialty_id,
            mode=body.mode or "system_composed",
            include_base_in_custom=body.include_base_in_custom if body.include_base_in_custom is not None else True,
        )
        db.add(st)
    else:
        if body.mode is not None:
            st.mode = body.mode
        if body.include_base_in_custom is not None:
            st.include_base_in_custom = body.include_base_in_custom
        st.medical_specialty_id = current_user.specialty_id

    want_merge = (body.mode == "system_composed") or (
        body.mode is None and st.mode == "system_composed"
    )
    if want_merge:
        try:
            materialize_system_composed(db, current_user)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    else:
        db.commit()

    return {"ok": True}


@router.get("/me/pool")
async def get_question_pool(
    current_user: User = Depends(require_doctor_user),
    db: Session = Depends(get_db),
):
    """Preguntas publicadas base + de la especialidad del doctor (para editor)."""
    if current_user.specialty_id is None:
        raise HTTPException(status_code=400, detail="Asigna primero tu especialidad.")
    sp = db.query(MedicalSpecialty).filter(MedicalSpecialty.id == current_user.specialty_id).first()
    if not sp:
        raise HTTPException(status_code=400, detail="Especialidad inválida.")

    base_v = latest_published_for_slug(db, "keepi_base")
    spec_v = latest_published_for_slug(db, specialty_slug_for_code(sp.code))
    if not base_v or not spec_v:
        raise HTTPException(status_code=503, detail="Catálogo de preguntas no disponible. Ejecuta el seed.")

    return {
        "base": [q.model_dump() for q in version_to_questions(db, base_v.id)],
        "specialty": [q.model_dump() for q in version_to_questions(db, spec_v.id)],
        "specialty_code": sp.code,
    }


@router.post("/me/custom/publish")
async def post_publish_custom(
    body: PublishCustomBody,
    current_user: User = Depends(require_doctor_user),
    db: Session = Depends(get_db),
):
    try:
        ver = publish_custom_from_payload(
            db,
            current_user,
            include_base=body.include_base,
            questions=body.questions,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"version_id": str(ver.id), "ok": True}


@router.get("/me/required", response_model=QuestionnaireRequiredResponse)
async def get_patient_required(
    current_user: User = Depends(require_patient_user),
    db: Session = Depends(get_db),
):
    if not current_user.created_by_user_id:
        return QuestionnaireRequiredResponse(required=False)

    doctor = db.query(User).filter(User.id == current_user.created_by_user_id).first()
    if not doctor:
        return QuestionnaireRequiredResponse(required=False)

    try:
        vid = ensure_doctor_active_version(db, doctor)
    except ValueError:
        return QuestionnaireRequiredResponse(required=False, title="", questions=[])

    done = (
        db.query(QuestionnaireResponse)
        .filter(
            QuestionnaireResponse.patient_id == current_user.id,
            QuestionnaireResponse.version_id == vid,
            QuestionnaireResponse.status == "submitted",
        )
        .first()
    )
    if done:
        return QuestionnaireRequiredResponse(required=False)

    draft = (
        db.query(QuestionnaireResponse)
        .filter(
            QuestionnaireResponse.patient_id == current_user.id,
            QuestionnaireResponse.version_id == vid,
            QuestionnaireResponse.status == "draft",
        )
        .first()
    )
    qs = version_to_questions(db, vid)
    return QuestionnaireRequiredResponse(
        required=True,
        version_id=str(vid),
        response_id=str(draft.id) if draft else None,
        status=draft.status if draft else None,
        title=version_title(db, vid),
        questions=qs,
    )


@router.post("/responses")
async def create_response(
    current_user: User = Depends(require_patient_user),
    db: Session = Depends(get_db),
):
    if not current_user.created_by_user_id:
        raise HTTPException(status_code=400, detail="Sin médico asociado.")

    doctor = db.query(User).filter(User.id == current_user.created_by_user_id).first()
    if not doctor:
        raise HTTPException(status_code=400, detail="Médico no encontrado.")

    try:
        vid = ensure_doctor_active_version(db, doctor)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    done = (
        db.query(QuestionnaireResponse)
        .filter(
            QuestionnaireResponse.patient_id == current_user.id,
            QuestionnaireResponse.version_id == vid,
            QuestionnaireResponse.status == "submitted",
        )
        .first()
    )
    if done:
        raise HTTPException(status_code=400, detail="Cuestionario ya enviado.")

    ex = (
        db.query(QuestionnaireResponse)
        .filter(
            QuestionnaireResponse.patient_id == current_user.id,
            QuestionnaireResponse.version_id == vid,
        )
        .first()
    )
    if ex:
        return {"response_id": str(ex.id), "version_id": str(vid)}

    row = QuestionnaireResponse(
        patient_id=current_user.id,
        version_id=vid,
        status="draft",
        created_by_doctor_id=doctor.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"response_id": str(row.id), "version_id": str(vid)}


@router.patch("/responses/{response_id}")
async def patch_response_answers(
    response_id: UUID,
    body: PatchAnswersBody,
    current_user: User = Depends(require_patient_user),
    db: Session = Depends(get_db),
):
    row = db.query(QuestionnaireResponse).filter(QuestionnaireResponse.id == response_id).first()
    if not row or row.patient_id != current_user.id:
        raise HTTPException(status_code=404, detail="Respuesta no encontrada.")
    if row.status != "draft":
        raise HTTPException(status_code=400, detail="Ya enviado.")

    for qid_str, val in body.answers.items():
        qid = UUID(qid_str)
        oa = (
            db.query(QuestionnaireAnswer)
            .filter(
                QuestionnaireAnswer.response_id == row.id,
                QuestionnaireAnswer.question_id == qid,
            )
            .first()
        )
        if oa:
            oa.value = val if isinstance(val, dict) else {"value": val}
        else:
            db.add(
                QuestionnaireAnswer(
                    response_id=row.id,
                    question_id=qid,
                    value=val if isinstance(val, dict) else {"value": val},
                )
            )
    db.commit()
    return {"ok": True}


@router.post("/responses/{response_id}/submit")
async def submit_response(
    response_id: UUID,
    current_user: User = Depends(require_patient_user),
    db: Session = Depends(get_db),
):
    from datetime import datetime, timezone

    row = db.query(QuestionnaireResponse).filter(QuestionnaireResponse.id == response_id).first()
    if not row or row.patient_id != current_user.id:
        raise HTTPException(status_code=404, detail="Respuesta no encontrada.")
    if row.status == "submitted":
        return {"ok": True}

    row.status = "submitted"
    row.submitted_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}
