from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.dto.consultation_context_dto import (
    ClinicalProfileUpdateRequest,
    ConsultationContextResponse,
    ConsultationStatsDto,
)
from app.models.doctor_patient_clinical_profile import DoctorPatientClinicalProfile
from app.models.questionnaire_invitation import QuestionnaireInvitation
from app.repositories.analysis_request_repository import AnalysisRequestRepository
from app.repositories.questionnaire_repository import QuestionnaireRepository
from app.repositories.user_repository import UserRepository
from app.services.medical.patient_timeline_service import PatientTimelineService


def _age_from_birth_date(raw: Any) -> Optional[int]:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            bd = datetime.strptime(s[:10], fmt).date()
            today = date.today()
            years = today.year - bd.year
            if (today.month, today.day) < (bd.month, bd.day):
                years -= 1
            return years if years >= 0 else None
        except ValueError:
            continue
    return None


def _numeric_from_answer(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value)
    match = re.search(r"[-+]?\d*\.?\d+", s.replace(",", "."))
    if not match:
        return None
    try:
        return float(match.group())
    except ValueError:
        return None


def _allergies_from_intake(saved: Dict[str, Any]) -> Optional[str]:
    section = saved.get("allergies")
    if not isinstance(section, dict):
        return None
    items = section.get("allergy_items")
    if isinstance(items, list):
        parts = []
        for item in items:
            if isinstance(item, str) and item.strip():
                parts.append(item.strip())
            elif isinstance(item, dict):
                name = str(item.get("name") or "").strip()
                if name:
                    parts.append(name)
        if parts:
            return ", ".join(parts)
    legacy = section.get("allergies")
    if isinstance(legacy, str) and legacy.strip():
        low = legacy.strip().lower()
        if low not in ("ninguna", "ninguno", "no", "n/a"):
            return legacy.strip()
    return None


def _phone_sex_from_intake(saved: Dict[str, Any]) -> Dict[str, Optional[str]]:
    personal = saved.get("personal_data")
    if not isinstance(personal, dict):
        personal = {}
    phone = personal.get("phone")
    sex = personal.get("sex")
    return {
        "phone": str(phone).strip() if phone else None,
        "sex": str(sex).strip() if sex else None,
    }


def _extract_intake_fields(
    ctx: Dict[str, Any], saved: Dict[str, Any]
) -> Dict[str, Any]:
    personal = saved.get("personal_data")
    if not isinstance(personal, dict):
        personal = {}
    birth = personal.get("birth_date") or ctx.get("birth_date")
    weight_raw = personal.get("weight_kg") or ctx.get("weight_kg")
    blood = personal.get("blood_type") or ctx.get("blood_type")
    return {
        "age_years": _age_from_birth_date(birth),
        "weight_kg": _numeric_from_answer(weight_raw),
        "blood_type": str(blood).strip() if blood else None,
        "allergies": _allergies_from_intake(saved),
    }


def _extract_questionnaire_kpis(rows: List[Any]) -> Dict[str, Any]:
    weight: Optional[float] = None
    blood_type: Optional[str] = None
    for row in rows:
        text = str(getattr(row, "question_text", "") or "").lower()
        value = getattr(row, "answer_value", None)
        if weight is None and "peso" in text:
            weight = _numeric_from_answer(value)
        if blood_type is None and (
            "tipo de sangre" in text
            or "grupo sangu" in text
            or ("sangre" in text and "presión" not in text)
        ):
            if value is not None:
                cleaned = str(value).strip()
                if cleaned and cleaned not in ("{}", "null"):
                    blood_type = cleaned
        if weight is not None and blood_type is not None:
            break
    return {"weight_kg": weight, "blood_type": blood_type}


def _pick(
    override: Optional[Any],
    intake: Optional[Any],
    questionnaire: Optional[Any],
) -> Optional[Any]:
    if override is not None and str(override).strip() != "":
        return override
    if intake is not None and str(intake).strip() != "":
        return intake
    if questionnaire is not None and str(questionnaire).strip() != "":
        return questionnaire
    return None


class ConsultationContextService:
    def __init__(self, db: Session) -> None:
        self._db = db
        self._users = UserRepository(db)

    def _ensure_patient(self, doctor_id: uuid.UUID, patient_id: uuid.UUID):
        patient = self._users.get_patient_owned_by_doctor(patient_id, doctor_id)
        if not patient:
            raise HTTPException(
                status_code=404,
                detail="Paciente no vinculado a su cuenta.",
            )
        return patient

    def _latest_intake(
        self, doctor_id: uuid.UUID, patient_id: uuid.UUID
    ) -> Optional[QuestionnaireInvitation]:
        return (
            self._db.query(QuestionnaireInvitation)
            .filter(
                QuestionnaireInvitation.doctor_id == doctor_id,
                QuestionnaireInvitation.patient_id == patient_id,
                QuestionnaireInvitation.intake_completed_at.isnot(None),
            )
            .order_by(QuestionnaireInvitation.intake_completed_at.desc())
            .first()
        )

    def _profile_row(
        self, doctor_id: uuid.UUID, patient_id: uuid.UUID
    ) -> Optional[DoctorPatientClinicalProfile]:
        return (
            self._db.query(DoctorPatientClinicalProfile)
            .filter(
                DoctorPatientClinicalProfile.doctor_id == doctor_id,
                DoctorPatientClinicalProfile.patient_id == patient_id,
            )
            .first()
        )

    def _stats(
        self, doctor_id: uuid.UUID, patient_id: uuid.UUID
    ) -> ConsultationStatsDto:
        analysis_repo = AnalysisRequestRepository(self._db)
        requests = analysis_repo.get_all_by_patient(patient_id)
        uploaded = sum(
            1
            for r in requests
            if r.status == "completed" and r.document_id is not None
        )
        pending = sum(
            1
            for r in requests
            if r.status == "pending" and r.document_id is None
        )
        timeline = PatientTimelineService(self._db).timeline_for_doctor_patient(
            doctor_id, patient_id
        )
        return ConsultationStatsDto(
            analysis_requested=len(requests),
            analysis_uploaded=uploaded,
            analysis_pending=pending,
            timeline_events=len(timeline),
        )

    def get_context(
        self, doctor_id: uuid.UUID, patient_id: uuid.UUID
    ) -> ConsultationContextResponse:
        patient = self._ensure_patient(doctor_id, patient_id)
        profile = self._profile_row(doctor_id, patient_id)
        intake = self._latest_intake(doctor_id, patient_id)

        intake_fields: Dict[str, Any] = {}
        contact_fields: Dict[str, Optional[str]] = {"phone": None, "sex": None}
        has_intake = intake is not None
        if intake is not None:
            ctx = (
                intake.intake_context
                if isinstance(intake.intake_context, dict)
                else {}
            )
            saved = (
                intake.intake_responses
                if isinstance(intake.intake_responses, dict)
                else {}
            )
            intake_fields = _extract_intake_fields(ctx, saved)
            contact_fields = _phone_sex_from_intake(saved)

        q_rows = QuestionnaireRepository(self._db).list_patient_completed_response_rows(
            patient_id, doctor_id
        )
        q_kpis = _extract_questionnaire_kpis(q_rows)

        age = _pick(
            profile.age_years if profile else None,
            intake_fields.get("age_years"),
            None,
        )
        blood = _pick(
            profile.blood_type if profile else None,
            intake_fields.get("blood_type"),
            q_kpis.get("blood_type"),
        )
        weight = _pick(
            profile.weight_kg if profile else None,
            intake_fields.get("weight_kg"),
            q_kpis.get("weight_kg"),
        )
        allergies = _pick(
            profile.allergies if profile else None,
            intake_fields.get("allergies"),
            None,
        )
        phone = _pick(
            profile.phone if profile else None,
            contact_fields.get("phone"),
            None,
        )
        sex = _pick(
            profile.sex if profile else None,
            contact_fields.get("sex"),
            None,
        )

        return ConsultationContextResponse(
            patient_name=patient.name if patient else None,
            patient_email=patient.email if patient else None,
            phone=str(phone).strip() if phone else None,
            sex=str(sex).strip() if sex else None,
            age_years=int(age) if age is not None else None,
            blood_type=str(blood).strip() if blood else None,
            weight_kg=float(weight) if weight is not None else None,
            allergies=str(allergies).strip() if allergies else None,
            has_clinical_intake=has_intake,
            stats=self._stats(doctor_id, patient_id),
        )

    def upsert_profile(
        self,
        doctor_id: uuid.UUID,
        patient_id: uuid.UUID,
        payload: ClinicalProfileUpdateRequest,
    ) -> ConsultationContextResponse:
        patient = self._ensure_patient(doctor_id, patient_id)
        row = self._profile_row(doctor_id, patient_id)
        if row is None:
            row = DoctorPatientClinicalProfile(
                doctor_id=doctor_id,
                patient_id=patient_id,
            )
            self._db.add(row)

        data = payload.model_dump(exclude_unset=True)
        user_fields = {}
        if "name" in data:
            user_fields["name"] = data.pop("name")
        if "email" in data:
            user_fields["email"] = data.pop("email")

        if user_fields.get("name") is not None:
            name = str(user_fields["name"]).strip()
            if name:
                patient.name = name

        if user_fields.get("email") is not None:
            email = str(user_fields["email"]).strip().lower()
            if email and email != patient.email:
                if self._users.email_exists(email):
                    raise HTTPException(
                        status_code=400,
                        detail="Ese correo ya está registrado.",
                    )
                patient.email = email

        for key, value in data.items():
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            setattr(row, key, value.strip() if isinstance(value, str) else value)

        self._db.commit()
        self._db.refresh(row)
        return self.get_context(doctor_id, patient_id)
