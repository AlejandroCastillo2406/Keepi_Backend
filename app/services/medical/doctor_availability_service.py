from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional, Tuple
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.appointment import Appointment
from app.models.doctor_scheduling import (
    AvailabilityRuleResponse,
    AvailabilityRuleItem,
    AvailabilitySlotResponse,
    ConsultationScheduleDayResponse,
    ConsultationScheduleResponse,
    DoctorAvailabilityRule,
    PatientSchedulingLinkResponse,
    PublicAvailabilityResponse,
    PublicBookAppointmentRequest,
    PublicBookAppointmentResponse,
    PublicSchedulingMetaResponse,
    SchedulingSettingsResponse,
)
from app.repositories.appointment_repository import AppointmentRepository
from app.repositories.doctor_scheduling_repository import DoctorSchedulingRepository
from app.repositories.procedure_block_repository import ProcedureBlockRepository
from app.services.medical.procedure_block_service import ProcedureBlockService
from app.repositories.procedure_block_repository import ProcedureBlockRepository


class DoctorAvailabilityService:
    MAX_RANGE_DAYS = 42

    @staticmethod
    def _sched_repo(db: Session) -> DoctorSchedulingRepository:
        return DoctorSchedulingRepository(db)

    @staticmethod
    def _appt_repo(db: Session) -> AppointmentRepository:
        return AppointmentRepository(db)

    @staticmethod
    def _hash_token(raw: str) -> str:
        return hashlib.sha256(raw.strip().encode("utf-8")).hexdigest()

    @staticmethod
    def get_settings(db: Session, doctor_id: UUID) -> SchedulingSettingsResponse:
        row = DoctorAvailabilityService._sched_repo(db).get_or_create_settings(doctor_id)
        return SchedulingSettingsResponse(
            slot_duration_minutes=row.slot_duration_minutes,
            timezone=row.timezone,
        )

    @staticmethod
    def update_settings(
        db: Session,
        doctor_id: UUID,
        slot_duration_minutes: int,
        tz: str,
    ) -> SchedulingSettingsResponse:
        row = DoctorAvailabilityService._sched_repo(db).update_settings(
            doctor_id, slot_duration_minutes, tz
        )
        return SchedulingSettingsResponse(
            slot_duration_minutes=row.slot_duration_minutes,
            timezone=row.timezone,
        )

    @staticmethod
    def list_rules(db: Session, doctor_id: UUID) -> List[AvailabilityRuleResponse]:
        rows = DoctorAvailabilityService._sched_repo(db).list_rules(doctor_id)
        return [
            AvailabilityRuleResponse(
                id=str(r.id),
                weekday=r.weekday,
                start_time=r.start_time.strftime("%H:%M"),
                end_time=r.end_time.strftime("%H:%M"),
                is_enabled=r.is_enabled,
            )
            for r in rows
        ]

    @staticmethod
    def get_consultation_schedule(
        db: Session, doctor_id: UUID
    ) -> ConsultationScheduleResponse:
        settings = DoctorAvailabilityService._sched_repo(db).get_or_create_settings(
            doctor_id
        )
        rules = DoctorAvailabilityService._sched_repo(db).list_rules(doctor_id)
        days = [
            ConsultationScheduleDayResponse(
                weekday=r.weekday,
                start_time=r.start_time.strftime("%H:%M"),
                end_time=r.end_time.strftime("%H:%M"),
            )
            for r in rules
            if r.is_enabled
        ]
        return ConsultationScheduleResponse(
            slot_duration_minutes=settings.slot_duration_minutes,
            days=days,
        )

    @staticmethod
    def replace_rules(
        db: Session, doctor_id: UUID, rules: List[AvailabilityRuleItem]
    ) -> List[AvailabilityRuleResponse]:
        for item in rules:
            if not item.is_enabled:
                continue
            start_parts = item.start_time.split(":")
            end_parts = item.end_time.split(":")
            start_m = int(start_parts[0]) * 60 + int(start_parts[1])
            end_m = int(end_parts[0]) * 60 + int(end_parts[1])
            if end_m <= start_m:
                raise HTTPException(
                    status_code=400,
                    detail=f"La hora fin debe ser posterior al inicio (día {item.weekday}).",
                )
        rows = DoctorAvailabilityService._sched_repo(db).replace_rules(doctor_id, rules)
        return DoctorAvailabilityService.list_rules(db, doctor_id)

    @staticmethod
    def _rules_by_weekday(
        rules: List[DoctorAvailabilityRule],
    ) -> dict[int, DoctorAvailabilityRule]:
        return {r.weekday: r for r in rules if r.is_enabled}

    @staticmethod
    def _slot_overlaps(
        slot_start: datetime,
        slot_end: datetime,
        appt: Appointment,
    ) -> bool:
        if appt.appointment_date is None or appt.end_date is None:
            return False
        return appt.appointment_date < slot_end and appt.end_date > slot_start

    @staticmethod
    def compute_available_slots(
        db: Session,
        doctor_id: UUID,
        from_date: date,
        to_date: date,
    ) -> Tuple[List[AvailabilitySlotResponse], Optional[str]]:
        if to_date < from_date:
            raise HTTPException(status_code=400, detail="Rango de fechas inválido.")
        if (to_date - from_date).days > DoctorAvailabilityService.MAX_RANGE_DAYS:
            raise HTTPException(
                status_code=400,
                detail=f"El rango máximo es {DoctorAvailabilityService.MAX_RANGE_DAYS} días.",
            )

        sched_repo = DoctorAvailabilityService._sched_repo(db)
        settings = sched_repo.get_or_create_settings(doctor_id)
        rules = sched_repo.list_enabled_rules(doctor_id)
        if not rules:
            return [], "El médico aún no publicó horarios de consulta."

        tz = ZoneInfo(settings.timezone)
        rules_map = DoctorAvailabilityService._rules_by_weekday(rules)
        duration = timedelta(minutes=settings.slot_duration_minutes)

        range_start = datetime.combine(from_date, datetime.min.time(), tzinfo=tz)
        range_end = datetime.combine(to_date, datetime.max.time(), tzinfo=tz)
        range_start_utc = range_start.astimezone(timezone.utc)
        range_end_utc = range_end.astimezone(timezone.utc)

        blocking = DoctorAvailabilityService._appt_repo(db).list_blocking_in_range(
            doctor_id, range_start_utc, range_end_utc
        )
        procedure_blocks = ProcedureBlockRepository(db).list_in_range(
            doctor_id, range_start_utc, range_end_utc
        )

        slots: List[AvailabilitySlotResponse] = []
        current = from_date
        now_utc = datetime.now(timezone.utc)

        while current <= to_date:
            weekday = current.weekday()
            rule = rules_map.get(weekday)
            if rule is not None:
                slot_start_local = datetime.combine(
                    current, rule.start_time, tzinfo=tz
                )
                day_end_local = datetime.combine(current, rule.end_time, tzinfo=tz)
                cursor = slot_start_local
                while cursor + duration <= day_end_local:
                    slot_end_local = cursor + duration
                    slot_start_utc = cursor.astimezone(timezone.utc)
                    slot_end_utc = slot_end_local.astimezone(timezone.utc)
                    if slot_start_utc > now_utc:
                        occupied = any(
                            DoctorAvailabilityService._slot_overlaps(
                                slot_start_utc, slot_end_utc, appt
                            )
                            for appt in blocking
                        ) or any(
                            ProcedureBlockService.overlaps_slot(
                                block, slot_start_utc, slot_end_utc
                            )
                            for block in procedure_blocks
                        )
                        if not occupied:
                            slots.append(
                                AvailabilitySlotResponse(
                                    start_at=slot_start_utc,
                                    end_at=slot_end_utc,
                                )
                            )
                    cursor += duration
            current += timedelta(days=1)

        return slots, None

    @staticmethod
    def resolve_token(db: Session, raw_token: str):
        token_hash = DoctorAvailabilityService._hash_token(raw_token)
        row = DoctorAvailabilityService._sched_repo(db).get_token_by_hash(token_hash)
        if row is None or not row.is_active:
            raise HTTPException(status_code=404, detail="Enlace de agendado no válido.")
        patient = row.patient
        doctor = row.doctor
        if patient is None or doctor is None:
            raise HTTPException(status_code=404, detail="Enlace de agendado no válido.")
        if patient.created_by_user_id != row.doctor_id:
            raise HTTPException(status_code=403, detail="Enlace no autorizado.")
        return row

    @staticmethod
    def get_public_meta(db: Session, raw_token: str) -> PublicSchedulingMetaResponse:
        row = DoctorAvailabilityService.resolve_token(db, raw_token)
        settings = DoctorAvailabilityService._sched_repo(db).get_or_create_settings(
            row.doctor_id
        )
        rules = DoctorAvailabilityService._sched_repo(db).list_enabled_rules(
            row.doctor_id
        )
        has_rules = len(rules) > 0
        return PublicSchedulingMetaResponse(
            doctor_name=row.doctor.name or "Tu médico",
            patient_name=row.patient.name or "Paciente",
            timezone=settings.timezone,
            slot_duration_minutes=settings.slot_duration_minutes,
            has_availability_rules=has_rules,
            message=None
            if has_rules
            else "El médico aún no publicó horarios de consulta.",
        )

    @staticmethod
    def get_public_availability(
        db: Session, raw_token: str, from_date: date, to_date: date
    ) -> PublicAvailabilityResponse:
        row = DoctorAvailabilityService.resolve_token(db, raw_token)
        slots, message = DoctorAvailabilityService.compute_available_slots(
            db, row.doctor_id, from_date, to_date
        )
        return PublicAvailabilityResponse(slots=slots, message=message)

    @staticmethod
    def book_public_slot(
        db: Session, raw_token: str, body: PublicBookAppointmentRequest
    ) -> PublicBookAppointmentResponse:
        row = DoctorAvailabilityService.resolve_token(db, raw_token)
        settings = DoctorAvailabilityService._sched_repo(db).get_or_create_settings(
            row.doctor_id
        )
        start_at = body.start_at
        if start_at.tzinfo is None:
            start_at = start_at.replace(tzinfo=timezone.utc)
        else:
            start_at = start_at.astimezone(timezone.utc)

        duration = timedelta(minutes=settings.slot_duration_minutes)
        end_at = start_at + duration

        if start_at <= datetime.now(timezone.utc):
            raise HTTPException(
                status_code=400, detail="El horario seleccionado ya no está disponible."
            )

        local_start = start_at.astimezone(ZoneInfo(settings.timezone))
        local_date = local_start.date()
        slots, msg = DoctorAvailabilityService.compute_available_slots(
            db, row.doctor_id, local_date, local_date
        )
        if msg and not slots:
            raise HTTPException(status_code=400, detail=msg)

        matched = any(
            abs((s.start_at - start_at).total_seconds()) < 1 for s in slots
        )
        if not matched:
            raise HTTPException(
                status_code=409,
                detail="Ese horario ya no está disponible. Elige otro.",
            )

        appt = Appointment(
            doctor_id=row.doctor_id,
            patient_id=row.patient_id,
            appointment_date=start_at,
            end_date=end_at,
            status="pending_doctor_approval",
            reason=(body.reason or "").strip() or "Consulta solicitada en línea",
        )
        appt = DoctorAvailabilityService._appt_repo(db).add(appt)

        from app.services.notificaciones.notification_service import NotificationService

        NotificationService(db).notify_user_push_in_app(
            row.doctor_id,
            title="Cita por confirmar",
            message=f"{row.patient.name or 'Un paciente'} solicitó cita para "
            f"{local_start.strftime('%d/%m/%Y %H:%M')}.",
            notification_type="appointment_pending_approval",
            payload={
                "appointment_id": str(appt.id),
                "action": "doctor_approve",
            },
            push_data={
                "type": "appointment_pending_approval",
                "appointment_id": str(appt.id),
            },
        )

        return PublicBookAppointmentResponse(
            appointment_id=str(appt.id),
            status=appt.status,
            message="Solicitud enviada. Tu médico confirmará la cita pronto.",
        )

    @staticmethod
    def create_patient_scheduling_token(
        db: Session, patient_id: UUID, doctor_id: UUID
    ) -> str:
        _, raw = DoctorAvailabilityService._sched_repo(db).create_or_get_scheduling_token(
            patient_id, doctor_id
        )
        return raw

    @staticmethod
    def build_patient_scheduling_link(
        db: Session, doctor_id: UUID, patient_id: UUID, *, patient_name: str
    ) -> PatientSchedulingLinkResponse:
        from app.services.notificaciones.patient_invite_email_service import (
            build_public_scheduling_link,
        )

        raw = DoctorAvailabilityService.create_patient_scheduling_token(
            db, patient_id, doctor_id
        )
        link = build_public_scheduling_link(raw)
        message = (
            "Comparte este enlace con el paciente para que agende citas en la web. "
            "Es permanente para este paciente."
            if link.startswith("http")
            else "Configura PUBLIC_QUESTIONNAIRE_BASE_URL en el servidor para obtener un enlace web completo."
        )
        return PatientSchedulingLinkResponse(
            scheduling_link=link,
            patient_name=patient_name,
            message=message,
        )
