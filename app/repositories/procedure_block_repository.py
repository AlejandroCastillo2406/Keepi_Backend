from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.doctor_procedure_block import DoctorProcedureBlock


class ProcedureBlockRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def add(self, row: DoctorProcedureBlock) -> DoctorProcedureBlock:
        self._db.add(row)
        self._db.commit()
        self._db.refresh(row)
        return row

    def delete(self, row: DoctorProcedureBlock) -> None:
        self._db.delete(row)
        self._db.commit()

    def get_by_id(self, block_id) -> Optional[DoctorProcedureBlock]:
        try:
            bid = (
                block_id
                if isinstance(block_id, uuid.UUID)
                else uuid.UUID(str(block_id))
            )
        except (ValueError, TypeError):
            return None
        return (
            self._db.query(DoctorProcedureBlock)
            .filter(DoctorProcedureBlock.id == bid)
            .first()
        )

    def list_in_range(
        self, doctor_id: uuid.UUID, start_at: datetime, end_at: datetime
    ) -> List[DoctorProcedureBlock]:
        return (
            self._db.query(DoctorProcedureBlock)
            .filter(DoctorProcedureBlock.doctor_id == doctor_id)
            .filter(DoctorProcedureBlock.start_at < end_at)
            .filter(DoctorProcedureBlock.end_at > start_at)
            .order_by(DoctorProcedureBlock.start_at.asc())
            .all()
        )
