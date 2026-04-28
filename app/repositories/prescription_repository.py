from __future__ import annotations

import uuid
from typing import List, Optional

from sqlalchemy.orm import Session, joinedload

from app.models.prescription import Prescription, PrescriptionItem


class PrescriptionRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def add(self, row: Prescription) -> Prescription:
        self._db.add(row)
        self._db.commit()
        self._db.refresh(row)
        return row

    def create_with_items(
        self, prescription: Prescription, items: List[PrescriptionItem]
    ) -> Prescription:
        self._db.add(prescription)
        self._db.flush()
        for it in items:
            it.prescription_id = prescription.id
            self._db.add(it)
        self._db.commit()
        self._db.refresh(prescription)
        return prescription

    def save(self, row: Prescription) -> Prescription:
        self._db.commit()
        self._db.refresh(row)
        return row

    def get_by_id(self, prescription_id: uuid.UUID) -> Optional[Prescription]:
        return (
            self._db.query(Prescription)
            .options(joinedload(Prescription.items))
            .filter(Prescription.id == prescription_id)
            .first()
        )

    def delete_items_for_prescription(self, prescription_id: uuid.UUID) -> None:
        self._db.query(PrescriptionItem).filter(
            PrescriptionItem.prescription_id == prescription_id
        ).delete()
        self._db.commit()

    def add_item(self, item: PrescriptionItem) -> PrescriptionItem:
        self._db.add(item)
        self._db.commit()
        self._db.refresh(item)
        return item

    def list_items_ordered(self, prescription_id: uuid.UUID) -> List[PrescriptionItem]:
        return (
            self._db.query(PrescriptionItem)
            .filter(PrescriptionItem.prescription_id == prescription_id)
            .order_by(PrescriptionItem.created_at.asc())
            .all()
        )

    def list_for_patient(self, patient_id: uuid.UUID) -> List[Prescription]:
        return (
            self._db.query(Prescription)
            .filter(Prescription.patient_id == patient_id)
            .order_by(Prescription.created_at.desc())
            .all()
        )

    def get_doctor_name(self, doctor_id: uuid.UUID) -> Optional[str]:
        from app.repositories.user_repository import UserRepository

        u = UserRepository(self._db).get_by_id_plain(doctor_id)
        return u.name if u else None

    def list_with_patient_reminders_enabled(self) -> List[Prescription]:
        return (
            self._db.query(Prescription)
            .filter(Prescription.patient_reminders_enabled.is_(True))
            .all()
        )
