from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone
from typing import Optional, Tuple
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.appointment_response_token import AppointmentPatientResponseToken


class AppointmentResponseTokenRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    @staticmethod
    def _hash_token(raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    @staticmethod
    def _generate_token() -> str:
        return secrets.token_urlsafe(32)

    def create_or_refresh(self, appointment_id: UUID) -> Tuple[AppointmentPatientResponseToken, str]:
        raw_token = self._generate_token()
        token_hash = self._hash_token(raw_token)
        existing = (
            self._db.query(AppointmentPatientResponseToken)
            .filter(AppointmentPatientResponseToken.appointment_id == appointment_id)
            .first()
        )
        if existing is not None:
            existing.token_hash = token_hash
            existing.response_action = None
            existing.responded_at = None
            self._db.commit()
            self._db.refresh(existing)
            return existing, raw_token

        row = AppointmentPatientResponseToken(
            appointment_id=appointment_id,
            token_hash=token_hash,
        )
        self._db.add(row)
        self._db.commit()
        self._db.refresh(row)
        return row, raw_token

    def get_by_raw_token(
        self, raw_token: str
    ) -> Optional[AppointmentPatientResponseToken]:
        stripped = (raw_token or "").strip()
        if not stripped:
            return None
        token_hash = self._hash_token(stripped)
        return (
            self._db.query(AppointmentPatientResponseToken)
            .filter(AppointmentPatientResponseToken.token_hash == token_hash)
            .first()
        )

    def mark_responded(
        self, row: AppointmentPatientResponseToken, action: str
    ) -> AppointmentPatientResponseToken:
        row.response_action = action
        row.responded_at = datetime.now(timezone.utc)
        self._db.commit()
        self._db.refresh(row)
        return row
