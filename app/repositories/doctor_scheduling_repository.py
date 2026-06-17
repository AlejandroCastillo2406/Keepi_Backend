from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import uuid
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.doctor_scheduling import (
    DoctorAvailabilityRule,
    DoctorSchedulingSettings,
    PatientSchedulingToken,
    parse_time_str,
)
from app.models.doctor_scheduling import AvailabilityRuleItem


class DoctorSchedulingRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    @staticmethod
    def _hash_token(raw_token: str) -> str:
        return hashlib.sha256(raw_token.strip().encode("utf-8")).hexdigest()

    @staticmethod
    def generate_raw_token() -> str:
        return secrets.token_urlsafe(32)

    @staticmethod
    def raw_token_for_pair(patient_id: uuid.UUID, doctor_id: uuid.UUID) -> str:
        from app.core.config import settings

        key = settings.jwt_secret_key.encode("utf-8")
        message = f"keepi-patient-scheduling-v1:{patient_id}:{doctor_id}".encode(
            "utf-8"
        )
        digest = hmac.new(key, message, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")

    def get_or_create_settings(self, doctor_id: uuid.UUID) -> DoctorSchedulingSettings:
        row = (
            self._db.query(DoctorSchedulingSettings)
            .filter(DoctorSchedulingSettings.doctor_id == doctor_id)
            .first()
        )
        if row is None:
            row = DoctorSchedulingSettings(doctor_id=doctor_id)
            self._db.add(row)
            self._db.commit()
            self._db.refresh(row)
        return row

    def update_settings(
        self,
        doctor_id: uuid.UUID,
        slot_duration_minutes: int,
        timezone: str,
    ) -> DoctorSchedulingSettings:
        row = self.get_or_create_settings(doctor_id)
        row.slot_duration_minutes = slot_duration_minutes
        row.timezone = timezone
        self._db.commit()
        self._db.refresh(row)
        return row

    def list_rules(self, doctor_id: uuid.UUID) -> List[DoctorAvailabilityRule]:
        return (
            self._db.query(DoctorAvailabilityRule)
            .filter(DoctorAvailabilityRule.doctor_id == doctor_id)
            .order_by(DoctorAvailabilityRule.weekday.asc())
            .all()
        )

    def replace_rules(
        self, doctor_id: uuid.UUID, rules: List[AvailabilityRuleItem]
    ) -> List[DoctorAvailabilityRule]:
        self._db.query(DoctorAvailabilityRule).filter(
            DoctorAvailabilityRule.doctor_id == doctor_id
        ).delete(synchronize_session=False)
        created: List[DoctorAvailabilityRule] = []
        for item in rules:
            row = DoctorAvailabilityRule(
                doctor_id=doctor_id,
                weekday=item.weekday,
                start_time=parse_time_str(item.start_time),
                end_time=parse_time_str(item.end_time),
                is_enabled=item.is_enabled,
            )
            self._db.add(row)
            created.append(row)
        self._db.commit()
        for row in created:
            self._db.refresh(row)
        return created

    def list_enabled_rules(self, doctor_id: uuid.UUID) -> List[DoctorAvailabilityRule]:
        return (
            self._db.query(DoctorAvailabilityRule)
            .filter(
                DoctorAvailabilityRule.doctor_id == doctor_id,
                DoctorAvailabilityRule.is_enabled.is_(True),
            )
            .order_by(DoctorAvailabilityRule.weekday.asc())
            .all()
        )

    def get_token_by_hash(self, token_hash: str) -> Optional[PatientSchedulingToken]:
        from sqlalchemy.orm import joinedload

        return (
            self._db.query(PatientSchedulingToken)
            .options(
                joinedload(PatientSchedulingToken.patient),
                joinedload(PatientSchedulingToken.doctor),
            )
            .filter(PatientSchedulingToken.token_hash == token_hash)
            .first()
        )

    def get_token_for_pair(
        self, patient_id: uuid.UUID, doctor_id: uuid.UUID
    ) -> Optional[PatientSchedulingToken]:
        return (
            self._db.query(PatientSchedulingToken)
            .filter(
                PatientSchedulingToken.patient_id == patient_id,
                PatientSchedulingToken.doctor_id == doctor_id,
            )
            .first()
        )

    def create_or_get_scheduling_token(
        self, patient_id: uuid.UUID, doctor_id: uuid.UUID
    ) -> Tuple[PatientSchedulingToken, str]:
        raw = self.raw_token_for_pair(patient_id, doctor_id)
        token_hash = self._hash_token(raw)
        existing = self.get_token_for_pair(patient_id, doctor_id)
        if existing is not None:
            if existing.token_hash != token_hash:
                existing.token_hash = token_hash
            if not existing.is_active:
                existing.is_active = True
            self._db.commit()
            self._db.refresh(existing)
            return existing, raw

        row = PatientSchedulingToken(
            patient_id=patient_id,
            doctor_id=doctor_id,
            token_hash=token_hash,
            is_active=True,
        )
        self._db.add(row)
        self._db.commit()
        self._db.refresh(row)
        return row, raw
