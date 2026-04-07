from typing import Optional

from sqlalchemy.orm import Session

from app.core.roles import ROLE_DOCTOR, ROLE_PATIENT
from app.models.patient_medical_record import (
    MedicalRecordPatientUpdate,
    MedicalRecordResponse,
    PatientMedicalRecord,
)
from app.models.user import User


class PatientMedicalRecordService:
    def __init__(self, db: Session):
        self.db = db

    def get_by_patient_id(self, patient_user_id: str) -> Optional[PatientMedicalRecord]:
        return (
            self.db.query(PatientMedicalRecord)
            .filter(PatientMedicalRecord.patient_user_id == patient_user_id)
            .first()
        )

    def get_response_for_patient(self, patient: User) -> MedicalRecordResponse:
        if patient.role is None or patient.role.name != ROLE_PATIENT:
            raise PermissionError("Solo pacientes tienen expediente en este módulo")
        row = self.get_by_patient_id(str(patient.id))
        if row is None:
            raise ValueError("No se encontró expediente médico")
        return MedicalRecordResponse.from_orm_record(row)

    def update_for_patient(self, patient: User, data: MedicalRecordPatientUpdate) -> MedicalRecordResponse:
        if patient.role is None or patient.role.name != ROLE_PATIENT:
            raise PermissionError("Solo el paciente puede actualizar su expediente")
        row = self.get_by_patient_id(str(patient.id))
        if row is None:
            raise ValueError("No se encontró expediente médico")
        payload = data.model_dump(exclude_unset=True)
        for key, value in payload.items():
            setattr(row, key, value)
        self.db.commit()
        self.db.refresh(row)
        return MedicalRecordResponse.from_orm_record(row)

    def get_response_for_doctor_patient(self, doctor: User, patient_id: str) -> MedicalRecordResponse:
        if doctor.role is None or doctor.role.name != ROLE_DOCTOR:
            raise PermissionError("Solo médicos pueden consultar expedientes de pacientes")
        patient = self.db.query(User).filter(User.id == patient_id).first()
        if patient is None:
            raise ValueError("Paciente no encontrado")
        if patient.role is None or patient.role.name != ROLE_PATIENT:
            raise ValueError("El usuario no es un paciente")
        if patient.created_by_user_id != doctor.id:
            raise PermissionError("Este paciente no fue registrado por ti")
        row = self.get_by_patient_id(str(patient.id))
        if row is None:
            raise ValueError("El paciente no tiene expediente médico")
        return MedicalRecordResponse.from_orm_record(row)
