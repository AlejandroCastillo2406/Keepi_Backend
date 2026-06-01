from __future__ import annotations

import uuid
from typing import List

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.dto.timeline_dto import PriorDocumentItemResponse, TimelineEventResponse
from app.repositories.patient_repository import PatientRepository
from app.repositories.user_repository import UserRepository
from app.services.medical.doctor_timeline_note_service import DoctorTimelineNoteService


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
        events = self._patient.get_timeline_events(self._db, str(patient_id))
        return DoctorTimelineNoteService(self._db).attach_notes_to_timeline(
            patient_id, events
        )

    def get_doctor_note_for_event(
        self,
        doctor_id: uuid.UUID,
        patient_id: uuid.UUID,
        timeline_event_id: str,
    ):
        return DoctorTimelineNoteService(self._db).get_note_content(
            doctor_id=doctor_id,
            patient_id=patient_id,
            timeline_event_id=timeline_event_id,
        )

    def upsert_doctor_note_for_event(
        self,
        doctor_id: uuid.UUID,
        patient_id: uuid.UUID,
        timeline_event_id: str,
        event_type: str,
        content: str,
    ):
        return DoctorTimelineNoteService(self._db).upsert_note_for_event(
            doctor_id=doctor_id,
            patient_id=patient_id,
            timeline_event_id=timeline_event_id,
            event_type=event_type,
            content=content,
        )

    def prior_documents_for_patient(self, patient_id: str) -> List[PriorDocumentItemResponse]:
        rows = self._patient.list_prior_documents_for_patient(self._db, patient_id)
        return [self._prior_doc_item(d) for d in rows]

    def prior_documents_for_doctor_patient(
        self, doctor_id: uuid.UUID, patient_id: uuid.UUID
    ) -> List[PriorDocumentItemResponse]:
        patient = self._users.get_patient_owned_by_doctor(patient_id, doctor_id)
        if not patient:
            raise HTTPException(
                status_code=404,
                detail="Paciente no vinculado a su cuenta.",
            )
        return self.prior_documents_for_patient(str(patient_id))

    @staticmethod
    def _prior_doc_item(doc) -> PriorDocumentItemResponse:
        created = getattr(doc, "created_at", None)
        return PriorDocumentItemResponse(
            id=str(doc.id),
            name=(doc.name or doc.file_name or "Documento"),
            file_name=doc.file_name,
            s3_key=doc.s3_key,
            file_size=doc.file_size,
            file_type=doc.file_type,
            created_at=created.isoformat() if created else None,
        )
