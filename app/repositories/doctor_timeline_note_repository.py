from __future__ import annotations

import uuid
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.doctor_timeline_note import DoctorTimelineNote


class DoctorTimelineNoteRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def create(self, row: DoctorTimelineNote) -> DoctorTimelineNote:
        self._db.add(row)
        self._db.commit()
        self._db.refresh(row)
        return row

    def save(self, row: DoctorTimelineNote) -> DoctorTimelineNote:
        self._db.commit()
        self._db.refresh(row)
        return row

    def get_for_patient_event(
        self, patient_id: uuid.UUID, timeline_event_id: str
    ) -> Optional[DoctorTimelineNote]:
        return (
            self._db.query(DoctorTimelineNote)
            .filter(
                DoctorTimelineNote.patient_id == patient_id,
                DoctorTimelineNote.timeline_event_id == timeline_event_id,
            )
            .first()
        )

    def map_by_event_ids(
        self, patient_id: uuid.UUID, event_ids: List[str]
    ) -> Dict[str, DoctorTimelineNote]:
        if not event_ids:
            return {}
        rows = (
            self._db.query(DoctorTimelineNote)
            .filter(
                DoctorTimelineNote.patient_id == patient_id,
                DoctorTimelineNote.timeline_event_id.in_(event_ids),
            )
            .all()
        )
        return {r.timeline_event_id: r for r in rows}
