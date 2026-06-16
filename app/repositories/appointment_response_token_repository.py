from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timezone
from typing import Optional, Tuple

from sqlalchemy.orm import Session, joinedload

from app.models.appointment import Appointment
from app.models.appointment_response_token import AppointmentPatientResponseToken


class AppointmentResponseTokenRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    @staticmethod
    def _hash_token(raw_token: str) -> str:
        return hashlib.sha256(raw_token.strip().encode("utf-8")).hexdigest()

    @staticmethod
    def generate_raw_token() -> str:
        return secrets.token_urlsafe(32)

    def create_or_rotate(self, appointment_id: uuid.UUID) -> Tuple[AppointmentPatientResponseToken, str]:
        existing = (
            self._db.query(AppointmentPatientResponseToken)
            .filter(AppointmentPatientResponseToken.appointment_id == appointment_id)
            .first()
        )
        raw = self.generate_raw_token()
        token_hash = self._hash_token(raw)
        if existing is not None:
            existing.token_hash = token_hash
            existing.response_action = None
            existing.responded_at = None
            self._db.commit()
            self._db.refresh(existing)
            return existing, raw

        row = AppointmentPatientResponseToken(
            appointment_id=appointment_id,
            token_hash=token_hash,
        )
        self._db.add(row)
        self._db.commit()
        self._db.refresh(row)
        return row, raw

    def resolve(self, raw_token: str) -> Tuple[AppointmentPatientResponseToken, Appointment]:
        token_hash = self._hash_token(raw_token)
        row = (
            self._db.query(AppointmentPatientResponseToken)
            .options(
                joinedload(AppointmentPatientResponseToken.appointment).joinedload(
                    Appointment.patient
                ),
                joinedload(AppointmentPatientResponseToken.appointment).joinedload(
                    Appointment.doctor
                ),
            )
            .filter(AppointmentPatientResponseToken.token_hash == token_hash)
            .first()
        )
        if row is None or row.appointment is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="Enlace no válido o expirado.")
        return row, row.appointment

    def mark_responded(
        self, row: AppointmentPatientResponseToken, action: str
    ) -> AppointmentPatientResponseToken:
        row.response_action = action
        row.responded_at = datetime.now(timezone.utc)
        self._db.commit()
        self._db.refresh(row)
        return row
