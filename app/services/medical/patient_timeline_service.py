from __future__ import annotations

import uuid
from typing import List

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.dto.timeline_dto import TimelineEventResponse
from app.repositories.patient_repository import PatientRepository
from app.repositories.user_repository import UserRepository


class PatientTimelineService:
    def __init__(
        self,
        db: Session,
        patient_repository: PatientRepository | None = None,
        user_repository: UserRepository | None = None,
    ) -> None:
        self._db = db
        self._patient = patient_repository or PatientRepository()
        self._users = user_repository or UserRepository(db)

    def timeline_for_patient(self, patient_id: str) -> List[TimelineEventResponse]:
        return self._patient.get_timeline_events(self._db, patient_id)

    def timeline_for_doctor_patient(
        self, doctor_id: uuid.UUID, patient_id: uuid.UUID
    ) -> List[TimelineEventResponse]:
        patient = self._users.get_patient_owned_by_doctor(patient_id, doctor_id)
        if not patient:
            raise HTTPException(
                status_code=404,
                detail="Paciente no vinculado a su cuenta.",
            )
        return self._patient.get_timeline_events(self._db, str(patient_id))
