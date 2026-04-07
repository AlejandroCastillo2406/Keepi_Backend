"""Lectura y actualización del expediente médico con reglas de acceso explícitas."""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.roles import ROLE_DOCTOR, ROLE_PATIENT
from app.models.patient_medical_record import (
    MedicalRecordPatch,
    MedicalRecordResponse,
    PatientMedicalRecord,
)
from app.models.user import User


class MedicalRecordService:
    def __init__(self, db: Session):
        self._db = db

    def get_for_patient_user(self, patient: User) -> Optional[PatientMedicalRecord]:
        return (
            self._db.query(PatientMedicalRecord)
            .filter(PatientMedicalRecord.patient_user_id == patient.id)
            .first()
        )

    def assert_doctor_owns_patient(self, doctor: User, patient_id: UUID) -> User:
        if doctor.role is None or doctor.role.name != ROLE_DOCTOR:
            raise PermissionError("Solo un médico puede consultar este expediente")
        patient = self._db.query(User).filter(User.id == patient_id).first()
        if patient is None:
            raise ValueError("Paciente no encontrado")
        if patient.role is None or patient.role.name != ROLE_PATIENT:
            raise ValueError("El usuario no es un paciente")
        if patient.created_by_user_id != doctor.id:
            raise PermissionError("No tienes acceso al expediente de este paciente")
        return patient

    def get_response_for_doctor(self, doctor: User, patient_id: UUID) -> MedicalRecordResponse:
        patient = self.assert_doctor_owns_patient(doctor, patient_id)
        row = self.get_for_patient_user(patient)
        if row is None:
            raise ValueError("Este paciente no tiene expediente registrado")
        return MedicalRecordResponse.from_orm_record(row)

    def get_response_for_patient(self, patient: User) -> MedicalRecordResponse:
        if patient.role is None or patient.role.name != ROLE_PATIENT:
            raise PermissionError("Solo los pacientes tienen expediente en esta ruta")
        row = self.get_for_patient_user(patient)
        if row is None:
            raise ValueError("No hay expediente asociado a tu cuenta")
        return MedicalRecordResponse.from_orm_record(row)

    def patch_by_patient(self, patient: User, patch: MedicalRecordPatch) -> MedicalRecordResponse:
        if patient.role is None or patient.role.name != ROLE_PATIENT:
            raise PermissionError("Solo el paciente puede editar su expediente aquí")
        row = self.get_for_patient_user(patient)
        if row is None:
            raise ValueError("No hay expediente asociado a tu cuenta")
        updates = patch.model_dump(exclude_unset=True)
        if not updates:
            raise ValueError("Envía al menos un campo para actualizar")
        for key, value in updates.items():
            setattr(row, key, value)
        self._db.commit()
        self._db.refresh(row)
        return MedicalRecordResponse.from_orm_record(row)
