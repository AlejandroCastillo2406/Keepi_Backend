from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.appointment import Appointment
from app.models.doctor_procedure_block import (
    DoctorProcedureBlock,
    ProcedureBlockCreateRequest,
    ProcedureBlockResponse,
)
from app.repositories.appointment_repository import AppointmentRepository
from app.repositories.procedure_block_repository import ProcedureBlockRepository


class ProcedureBlockService:
    @staticmethod
    def _repo(db: Session) -> ProcedureBlockRepository:
        return ProcedureBlockRepository(db)

    @staticmethod
    def _appt_repo(db: Session) -> AppointmentRepository:
        return AppointmentRepository(db)

    @staticmethod
    def _normalize(dt: datetime) -> datetime:
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    @staticmethod
    def _ranges_overlap(
        start_a: datetime, end_a: datetime, start_b: datetime, end_b: datetime
    ) -> bool:
        return start_a < end_b and end_a > start_b

    @staticmethod
    def _assert_no_conflicts(
        db: Session,
        doctor_id: UUID,
        start_at: datetime,
        end_at: datetime,
        *,
        exclude_block_id: UUID | None = None,
    ) -> None:
        blocking = ProcedureBlockService._appt_repo(db).list_blocking_in_range(
            doctor_id, start_at, end_at
        )
        for appt in blocking:
            if appt.appointment_date is None or appt.end_date is None:
                continue
            if ProcedureBlockService._ranges_overlap(
                start_at, end_at, appt.appointment_date, appt.end_date
            ):
                raise HTTPException(
                    status_code=409,
                    detail="El horario se solapa con una cita existente.",
                )

        procedures = ProcedureBlockService._repo(db).list_in_range(
            doctor_id, start_at, end_at
        )
        for block in procedures:
            if exclude_block_id is not None and block.id == exclude_block_id:
                continue
            if ProcedureBlockService._ranges_overlap(
                start_at, end_at, block.start_at, block.end_at
            ):
                raise HTTPException(
                    status_code=409,
                    detail="El horario se solapa con otro procedimiento.",
                )

    @staticmethod
    def list_for_calendar(
        db: Session, doctor_id: UUID, start_at: datetime, end_at: datetime
    ) -> list[ProcedureBlockResponse]:
        rows = ProcedureBlockService._repo(db).list_in_range(
            doctor_id, start_at, end_at
        )
        return [ProcedureBlockResponse.from_entity(r) for r in rows]

    @staticmethod
    def create(
        db: Session, doctor_id: UUID, body: ProcedureBlockCreateRequest
    ) -> ProcedureBlockResponse:
        title = body.title.strip()
        if not title:
            raise HTTPException(status_code=400, detail="El título es obligatorio.")

        start_at = ProcedureBlockService._normalize(body.start_at)
        end_at = ProcedureBlockService._normalize(body.end_at)
        if end_at <= start_at:
            raise HTTPException(
                status_code=400,
                detail="La hora de fin debe ser posterior a la de inicio.",
            )

        ProcedureBlockService._assert_no_conflicts(db, doctor_id, start_at, end_at)

        row = DoctorProcedureBlock(
            doctor_id=doctor_id,
            title=title,
            start_at=start_at,
            end_at=end_at,
        )
        saved = ProcedureBlockService._repo(db).add(row)
        return ProcedureBlockResponse.from_entity(saved)

    @staticmethod
    def delete(db: Session, doctor_id: UUID, block_id: UUID) -> None:
        row = ProcedureBlockService._repo(db).get_by_id(block_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Procedimiento no encontrado.")
        if row.doctor_id != doctor_id:
            raise HTTPException(status_code=403, detail="No autorizado.")
        ProcedureBlockService._repo(db).delete(row)

    @staticmethod
    def overlaps_slot(
        block: DoctorProcedureBlock, slot_start: datetime, slot_end: datetime
    ) -> bool:
        return ProcedureBlockService._ranges_overlap(
            slot_start, slot_end, block.start_at, block.end_at
        )

    @staticmethod
    def overlaps_appointment(
        appt: Appointment, slot_start: datetime, slot_end: datetime
    ) -> bool:
        if appt.appointment_date is None or appt.end_date is None:
            return False
        return ProcedureBlockService._ranges_overlap(
            slot_start, slot_end, appt.appointment_date, appt.end_date
        )
