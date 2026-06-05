from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.appointment import Appointment


class AppointmentRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def add(self, row: Appointment) -> Appointment:
        self._db.add(row)
        self._db.commit()
        self._db.refresh(row)
        return row

    def save(self, row: Appointment) -> Appointment:
        self._db.commit()
        self._db.refresh(row)
        return row

    def get_by_id(self, appointment_id) -> Optional[Appointment]:
        try:
            aid = (
                appointment_id
                if isinstance(appointment_id, uuid.UUID)
                else uuid.UUID(str(appointment_id))
            )
        except (ValueError, TypeError):
            return None
        return self._db.query(Appointment).filter(Appointment.id == aid).first()

    def list_by_patient(self, patient_id: uuid.UUID) -> List[Appointment]:
        return (
            self._db.query(Appointment)
            .filter(Appointment.patient_id == patient_id)
            .order_by(Appointment.appointment_date.desc())
            .all()
        )

    def list_doctor_calendar(
        self, doctor_id: uuid.UUID, start_at: datetime, end_at: datetime
    ) -> List[Appointment]:
        return (
            self._db.query(Appointment)
            .filter(Appointment.doctor_id == doctor_id)
            .filter(
                or_(
                    Appointment.appointment_date.is_(None),
                    Appointment.appointment_date.between(start_at, end_at),
                )
            )
            .order_by(Appointment.created_at.desc())
            .all()
        )

    _BLOCKING_STATUSES = (
        "scheduled",
        "pending_patient_approval",
        "pending_doctor_approval",
    )

    def list_blocking_in_range(
        self, doctor_id: uuid.UUID, start_at: datetime, end_at: datetime
    ) -> List[Appointment]:
        return (
            self._db.query(Appointment)
            .filter(Appointment.doctor_id == doctor_id)
            .filter(Appointment.status.in_(self._BLOCKING_STATUSES))
            .filter(Appointment.appointment_date.isnot(None))
            .filter(Appointment.appointment_date < end_at)
            .filter(Appointment.end_date > start_at)
            .all()
        )
