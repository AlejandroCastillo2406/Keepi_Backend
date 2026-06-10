from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

import boto3
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.dto.timeline_dto import TimelineEventResponse
from app.models.doctor_timeline_note import (
    DoctorTimelineNote,
    DoctorTimelineNoteResponse,
)
from app.repositories.doctor_timeline_note_repository import DoctorTimelineNoteRepository
from app.repositories.user_repository import UserRepository
from app.utils.doctor_patient_storage import (
    build_doctor_timeline_note_filename,
    doctor_patient_notes_s3_key,
    patient_folder_label,
)

logger = logging.getLogger(__name__)

_PREVIEW_MAX = 160


class DoctorTimelineNoteService:
    def __init__(self, db: Session) -> None:
        self._db = db
        self._repo = DoctorTimelineNoteRepository(db)
        self._users = UserRepository(db)
        self._s3 = boto3.client(
            "s3",
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.aws_region,
        )

    @staticmethod
    def _preview(text: str) -> str:
        t = (text or "").strip()
        if "--- KEEPIMETRICAS ---" in t:
            t = t.split("--- KEEPIMETRICAS ---", 1)[0].strip()
        if len(t) <= _PREVIEW_MAX:
            return t
        return t[: _PREVIEW_MAX - 1].rstrip() + "…"

    def attach_notes_to_timeline(
        self, patient_id: uuid.UUID, events: List[TimelineEventResponse]
    ) -> List[TimelineEventResponse]:
        if not events:
            return events
        note_map = self._repo.map_by_event_ids(
            patient_id, [e.id for e in events]
        )
        if not note_map:
            return events
        enriched: List[TimelineEventResponse] = []
        for ev in events:
            note = note_map.get(ev.id)
            if note is None:
                enriched.append(ev)
                continue
            enriched.append(
                ev.model_copy(
                    update={
                        "has_doctor_note": True,
                        "doctor_note_preview": note.content_preview or None,
                    }
                )
            )
        return enriched

    def save_note_for_event(
        self,
        *,
        doctor_id: uuid.UUID,
        patient_id: uuid.UUID,
        timeline_event_id: str,
        event_type: str,
        content: str,
    ) -> Optional[DoctorTimelineNote]:
        text = (content or "").strip()
        if not text:
            return None

        patient = self._users.get_by_id_plain(patient_id)
        if patient is None:
            raise HTTPException(status_code=404, detail="Paciente no encontrado")

        existing = self._repo.get_for_patient_event(patient_id, timeline_event_id)
        if existing is not None:
            return self._write_note_content(
                note=existing,
                doctor_id=doctor_id,
                patient=patient,
                timeline_event_id=timeline_event_id,
                event_type=event_type,
                text=text,
            )

        created_at = datetime.now(timezone.utc)
        note_id = str(uuid.uuid4())
        patient_label = patient_folder_label(patient)
        filename = build_doctor_timeline_note_filename(
            event_type=event_type,
            created_at=created_at,
            note_id=note_id,
        )
        s3_key = doctor_patient_notes_s3_key(
            str(doctor_id), patient_label, filename
        )
        self._put_note_s3(
            s3_key=s3_key,
            patient=patient,
            timeline_event_id=timeline_event_id,
            event_type=event_type,
            text=text,
            created_at=created_at,
        )

        row = DoctorTimelineNote(
            id=uuid.UUID(note_id),
            doctor_id=doctor_id,
            patient_id=patient_id,
            timeline_event_id=timeline_event_id,
            event_type=(event_type or "")[:40],
            s3_key=s3_key,
            content_preview=self._preview(text),
        )
        return self._repo.create(row)

    def upsert_note_for_event(
        self,
        *,
        doctor_id: uuid.UUID,
        patient_id: uuid.UUID,
        timeline_event_id: str,
        event_type: str,
        content: str,
    ) -> DoctorTimelineNoteResponse:
        note = self.save_note_for_event(
            doctor_id=doctor_id,
            patient_id=patient_id,
            timeline_event_id=timeline_event_id,
            event_type=event_type,
            content=content,
        )
        if note is None:
            raise HTTPException(status_code=400, detail="La nota no puede estar vacía")
        return self.get_note_content(
            doctor_id=doctor_id,
            patient_id=patient_id,
            timeline_event_id=timeline_event_id,
        )

    def _put_note_s3(
        self,
        *,
        s3_key: str,
        patient,
        timeline_event_id: str,
        event_type: str,
        text: str,
        created_at: datetime,
    ) -> None:
        header = (
            f"Paciente: {patient.name}\n"
            f"Evento: {timeline_event_id}\n"
            f"Tipo: {event_type}\n"
            f"Fecha: {created_at.isoformat()}\n"
            f"---\n"
        )
        body = header + text
        try:
            self._s3.put_object(
                Bucket=settings.aws_s3_bucket,
                Key=s3_key,
                Body=body.encode("utf-8"),
                ContentType="text/plain; charset=utf-8",
            )
        except Exception as e:
            logger.exception("Error guardando nota en S3: %s", e)
            raise HTTPException(
                status_code=500,
                detail="No se pudo guardar la nota en almacenamiento",
            ) from e

    def _write_note_content(
        self,
        *,
        note: DoctorTimelineNote,
        doctor_id: uuid.UUID,
        patient,
        timeline_event_id: str,
        event_type: str,
        text: str,
    ) -> DoctorTimelineNote:
        updated_at = datetime.now(timezone.utc)
        s3_key = note.s3_key
        if s3_key and not s3_key.startswith("users/"):
            s3_key = f"users/{doctor_id}/{s3_key.lstrip('/')}"
            note.s3_key = s3_key
        self._put_note_s3(
            s3_key=s3_key,
            patient=patient,
            timeline_event_id=timeline_event_id,
            event_type=event_type or note.event_type,
            text=text,
            created_at=updated_at,
        )
        note.content_preview = self._preview(text)
        note.event_type = (event_type or note.event_type or "")[:40]
        return self._repo.save(note)

    def get_note_content(
        self,
        *,
        doctor_id: uuid.UUID,
        patient_id: uuid.UUID,
        timeline_event_id: str,
    ) -> DoctorTimelineNoteResponse:
        patient = self._users.get_patient_owned_by_doctor(patient_id, doctor_id)
        if patient is None:
            raise HTTPException(
                status_code=404,
                detail="Paciente no vinculado a su cuenta.",
            )

        note = self._repo.get_for_patient_event(patient_id, timeline_event_id)
        if note is None:
            raise HTTPException(
                status_code=404,
                detail="No hay nota del médico para este evento",
            )

        s3_key = note.s3_key
        if s3_key and not s3_key.startswith("users/"):
            s3_key = f"users/{doctor_id}/{s3_key.lstrip('/')}"

        try:
            obj = self._s3.get_object(
                Bucket=settings.aws_s3_bucket,
                Key=s3_key,
            )
            raw = obj["Body"].read().decode("utf-8", errors="replace")
        except Exception as e:
            logger.warning("No se pudo leer nota S3 %s: %s", s3_key, e)
            raw = note.content_preview

        if "---\n" in raw:
            content = raw.split("---\n", 1)[1].strip()
        else:
            content = raw.strip()

        return DoctorTimelineNoteResponse(
            event_id=timeline_event_id,
            content=content,
            created_at=note.created_at,
            doctor_id=str(note.doctor_id),
        )
