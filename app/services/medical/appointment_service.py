from datetime import datetime, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.appointment import (
    Appointment,
    AppointmentCreateRequest,
    AppointmentDoctorProposeRequest,
    AppointmentDoctorRescheduleRequest,
    AppointmentPatientCreateRequest,
    AppointmentPatientRespondRequest,
    PublicAppointmentMetaResponse,
    PublicAppointmentRespondRequest,
    PublicAppointmentRespondResponse,
)
from app.repositories.appointment_repository import AppointmentRepository
from app.dto.consultation_context_dto import AttendanceStatsDto
from app.utils.attendance_stats import attendance_counts


class AppointmentService:

    @staticmethod
    def _repo(db: Session) -> AppointmentRepository:
        return AppointmentRepository(db)

    @staticmethod
    def create_patient_request(
        db: Session, patient_id: str, request_data: AppointmentPatientCreateRequest
    ) -> Appointment:
        new_appointment = Appointment(
            patient_id=patient_id,
            doctor_id=request_data.doctor_id,
            reason=request_data.reason,
            status="pending_doctor_proposal",
        )
        return AppointmentService._repo(db).add(new_appointment)

    @staticmethod
    def propose_doctor_time(
        db: Session,
        appointment_id: str,
        doctor_id: str,
        proposal_data: AppointmentDoctorProposeRequest,
    ) -> Appointment:
        repo = AppointmentService._repo(db)
        appointment = repo.get_by_id(appointment_id)

        if not appointment:
            raise HTTPException(status_code=404, detail="Cita no encontrada")

        if str(appointment.doctor_id) != doctor_id:
            raise HTTPException(
                status_code=403, detail="No tienes permiso para modificar esta cita"
            )

        if appointment.status != "pending_doctor_proposal":
            raise HTTPException(
                status_code=400, detail="Esta cita no está esperando propuesta"
            )

        appointment.appointment_date = proposal_data.proposed_start_at
        appointment.end_date = proposal_data.proposed_start_at + timedelta(
            minutes=proposal_data.duration_minutes
        )
        appointment.status = "pending_patient_approval"

        return repo.save(appointment)

    @staticmethod
    def respond_to_proposal(
        db: Session,
        appointment_id: str,
        patient_id: str,
        response_data: AppointmentPatientRespondRequest,
    ) -> Appointment:
        repo = AppointmentService._repo(db)
        appointment = repo.get_by_id(appointment_id)

        if not appointment:
            raise HTTPException(status_code=404, detail="Cita no encontrada")

        if str(appointment.patient_id) != patient_id:
            raise HTTPException(
                status_code=403, detail="No tienes permiso para modificar esta cita"
            )

        if appointment.status != "pending_patient_approval":
            raise HTTPException(
                status_code=400, detail="Esta cita no tiene una propuesta pendiente"
            )

        if response_data.action == "accept":
            appointment.status = "scheduled"
        elif response_data.action == "reject":
            appointment.status = "canceled"

        saved = repo.save(appointment)
        if response_data.action == "accept":
            from app.repositories.user_repository import UserRepository

            doctor = UserRepository(db).get_by_id_with_role(appointment.doctor_id)
            doctor_name = (doctor.name or "").strip() if doctor else "Tu médico"
            AppointmentService._send_confirmed_email_to_patient(
                db,
                saved,
                doctor_name=doctor_name,
                confirmed_from_web=False,
            )
        return saved

    @staticmethod
    def get_appointments_by_patient(db: Session, patient_id: str):
        return AppointmentService._repo(db).list_by_patient(UUID(str(patient_id)))

    @staticmethod
    def create_doctor_appointment(
        db: Session,
        doctor_id: UUID,
        body: AppointmentCreateRequest,
    ) -> Appointment:
        start_at = body.appointment_date
        end_at = start_at + timedelta(minutes=body.duration_minutes)
        row = Appointment(
            doctor_id=doctor_id,
            patient_id=UUID(body.patient_id),
            appointment_date=start_at,
            end_date=end_at,
            status="scheduled",
            reason=body.reason.strip() or "Consulta médica",
        )
        return AppointmentService._repo(db).add(row)

    @staticmethod
    def notify_patient_doctor_scheduled(
        db: Session,
        appointment: Appointment,
        *,
        doctor_name: str,
    ) -> None:
        """Aviso al paciente cuando el doctor agenda en la app (cita ya confirmada)."""
        from app.repositories.user_repository import UserRepository
        from app.services.medical.doctor_availability_service import (
            DoctorAvailabilityService,
        )
        from app.services.notificaciones.appointment_email_service import (
            _format_slot_range,
            send_doctor_scheduled_appointment_email,
        )
        from app.services.notificaciones.notification_service import NotificationService

        patient = UserRepository(db).get_by_id_with_role(appointment.patient_id)
        if patient is None:
            return

        settings = DoctorAvailabilityService.get_settings(db, appointment.doctor_id)
        when_label = _format_slot_range(
            appointment.appointment_date,
            appointment.end_date,
            timezone=settings.timezone,
        )
        patient_name = (patient.name or "").strip() or "Paciente"
        reason = (appointment.reason or "").strip() or "Consulta médica"

        NotificationService(db).notify_user_push_in_app(
            appointment.patient_id,
            title="Cita confirmada",
            message=(
                f"El Dr. {(doctor_name or '').strip() or 'tu médico'} "
                f"programó tu consulta para {when_label}."
            ),
            notification_type="appointment_confirmed",
            payload={
                "type": "appointment_confirmed",
                "appointment_id": str(appointment.id),
            },
            push_data={
                "type": "appointment_confirmed",
                "appointment_id": str(appointment.id),
            },
        )

        email = (patient.email or "").strip()
        if email:
            send_doctor_scheduled_appointment_email(
                to_email=email,
                patient_name=patient_name,
                doctor_name=doctor_name,
                reason=reason,
                when_label=when_label,
                confirmed_from_web=False,
            )

    @staticmethod
    def _send_confirmed_email_to_patient(
        db: Session,
        appointment: Appointment,
        *,
        doctor_name: str,
        confirmed_from_web: bool = False,
    ) -> None:
        from app.repositories.user_repository import UserRepository
        from app.services.medical.doctor_availability_service import (
            DoctorAvailabilityService,
        )
        from app.services.notificaciones.appointment_email_service import (
            _format_slot_range,
            send_doctor_scheduled_appointment_email,
        )

        patient = UserRepository(db).get_by_id_with_role(appointment.patient_id)
        if patient is None:
            return
        settings = DoctorAvailabilityService.get_settings(db, appointment.doctor_id)
        when_label = _format_slot_range(
            appointment.appointment_date,
            appointment.end_date,
            timezone=settings.timezone,
        )
        patient_name = (patient.name or "").strip() or "Paciente"
        reason = (appointment.reason or "").strip() or "Consulta médica"
        email = (patient.email or "").strip()
        if not email:
            return
        send_doctor_scheduled_appointment_email(
            to_email=email,
            patient_name=patient_name,
            doctor_name=doctor_name,
            reason=reason,
            when_label=when_label,
            confirmed_from_web=confirmed_from_web,
        )

    @staticmethod
    def _notify_patient_proposal(
        db: Session,
        appointment: Appointment,
        *,
        doctor_name: str,
        raw_token: str,
    ) -> None:
        from app.repositories.user_repository import UserRepository
        from app.services.medical.doctor_availability_service import (
            DoctorAvailabilityService,
        )
        from app.services.notificaciones.appointment_email_service import (
            _format_slot_range,
            build_public_appointment_link,
            send_appointment_proposal_email,
        )
        from app.services.notificaciones.notification_service import NotificationService

        patient = UserRepository(db).get_by_id_with_role(appointment.patient_id)
        if patient is None:
            return

        settings = DoctorAvailabilityService.get_settings(db, appointment.doctor_id)
        when_label = _format_slot_range(
            appointment.appointment_date,
            appointment.end_date,
            timezone=settings.timezone,
        )
        patient_name = (patient.name or "").strip() or "Paciente"
        reason = (appointment.reason or "").strip() or "Consulta médica"

        NotificationService(db).notify_user_push_in_app(
            appointment.patient_id,
            title="Propuesta de cita",
            message=(
                f"El Dr. {(doctor_name or '').strip() or 'tu médico'} "
                f"te propone una cita para {when_label}."
            ),
            notification_type="appointment_proposed",
            payload={
                "type": "appointment_proposed",
                "appointment_id": str(appointment.id),
                "action": "patient_decision",
            },
            push_data={
                "type": "appointment_proposed",
                "appointment_id": str(appointment.id),
            },
        )

        email = (patient.email or "").strip()
        if email:
            response_link = build_public_appointment_link(raw_token)
            send_appointment_proposal_email(
                to_email=email,
                patient_name=patient_name,
                doctor_name=doctor_name,
                reason=reason,
                when_label=when_label,
                response_link=response_link,
            )

    @staticmethod
    def _send_rejection_email_to_patient(
        db: Session,
        appointment: Appointment,
        *,
        doctor_name: str,
    ) -> None:
        from app.repositories.user_repository import UserRepository
        from app.services.medical.doctor_availability_service import (
            DoctorAvailabilityService,
        )
        from app.services.notificaciones.appointment_email_service import (
            _format_slot_range,
            send_appointment_rejection_email,
        )
        from app.services.notificaciones.patient_invite_email_service import (
            build_public_scheduling_link,
        )

        patient = UserRepository(db).get_by_id_with_role(appointment.patient_id)
        if patient is None:
            return

        settings = DoctorAvailabilityService.get_settings(db, appointment.doctor_id)
        when_label = _format_slot_range(
            appointment.appointment_date,
            appointment.end_date,
            timezone=settings.timezone,
        )
        patient_name = (patient.name or "").strip() or "Paciente"
        reason = (appointment.reason or "").strip() or "Consulta médica"
        email = (patient.email or "").strip()
        if not email:
            return

        raw_token = DoctorAvailabilityService.create_patient_scheduling_token(
            db,
            appointment.patient_id,
            appointment.doctor_id,
        )
        scheduling_link = build_public_scheduling_link(raw_token)
        send_appointment_rejection_email(
            to_email=email,
            patient_name=patient_name,
            doctor_name=doctor_name,
            reason=reason,
            when_label=when_label,
            scheduling_link=scheduling_link,
        )

    @staticmethod
    def list_doctor_calendar(
        db: Session, doctor_id: UUID, start_at: datetime, end_at: datetime
    ):
        return AppointmentService._repo(db).list_doctor_calendar(
            doctor_id, start_at, end_at
        )

    @staticmethod
    def list_patient_appointments(db: Session, patient_id: UUID):
        return AppointmentService._repo(db).list_by_patient(patient_id)

    @staticmethod
    def list_doctor_patient_appointments(
        db: Session, doctor_id: UUID, patient_id: UUID
    ):
        from app.services.medical.consultation_context_service import (
            ConsultationContextService,
        )

        ConsultationContextService(db)._ensure_patient(doctor_id, patient_id)
        rows = AppointmentService._repo(db).list_by_doctor_and_patient(
            doctor_id, patient_id
        )
        return rows

    @staticmethod
    def get_appointment_for_patient(
        db: Session, appointment_id: UUID, patient_id: UUID
    ) -> Appointment:
        repo = AppointmentService._repo(db)
        row = repo.get_by_id(appointment_id)
        if row is None or row.patient_id != patient_id:
            raise HTTPException(status_code=404, detail="Cita no encontrada.")
        return row

    @staticmethod
    def get_appointment_for_user(
        db: Session, appointment_id: UUID, user_id: UUID, role_name: str | None
    ) -> Appointment:
        from app.core.roles import ROLE_DOCTOR, ROLE_PATIENT

        repo = AppointmentService._repo(db)
        row = repo.get_by_id(appointment_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Cita no encontrada.")

        if role_name == ROLE_PATIENT and row.patient_id == user_id:
            return row
        if role_name == ROLE_DOCTOR and row.doctor_id == user_id:
            return row

        raise HTTPException(status_code=404, detail="Cita no encontrada.")

    @staticmethod
    def get_doctor_attendance_stats(db: Session, doctor_id: UUID) -> AttendanceStatsDto:
        attended, no_show = AppointmentService._repo(db).count_attendance(doctor_id)
        attended, no_show, rate = attendance_counts(attended, no_show)
        return AttendanceStatsDto(
            appointments_attended=attended,
            appointments_no_show=no_show,
            attendance_rate_percent=rate,
        )

    @staticmethod
    def record_attendance(
        db: Session,
        appointment_id: UUID,
        doctor_id: UUID,
        status: str,
    ) -> Appointment:
        from datetime import timezone

        from app.services.medical.doctor_availability_service import (
            DoctorAvailabilityService,
        )

        repo = AppointmentService._repo(db)
        row = repo.get_by_id(appointment_id)
        if row is None or row.doctor_id != doctor_id:
            raise HTTPException(status_code=404, detail="Cita no encontrada.")
        if row.status != "scheduled":
            raise HTTPException(
                status_code=400,
                detail="Solo se puede registrar asistencia en citas confirmadas.",
            )
        if row.attendance_status:
            raise HTTPException(
                status_code=400,
                detail="La asistencia de esta cita ya fue registrada.",
            )
        start = row.appointment_date
        if start is None:
            raise HTTPException(status_code=400, detail="La cita no tiene fecha.")
        end = row.end_date
        if end is None:
            settings = DoctorAvailabilityService.get_settings(db, doctor_id)
            end = start + timedelta(minutes=settings.slot_duration_minutes)
        now = datetime.now(timezone.utc)
        if now < end:
            raise HTTPException(
                status_code=400,
                detail="Aún no ha terminado el horario de la cita.",
            )
        if status not in ("attended", "no_show"):
            raise HTTPException(status_code=400, detail="Estado de asistencia inválido.")
        row.attendance_status = status
        return repo.save(row)

    @staticmethod
    def doctor_propose_and_notify(
        db: Session,
        appointment_id: UUID,
        doctor_id: UUID,
        body: AppointmentDoctorProposeRequest,
        doctor_name: str,
    ) -> Appointment:
        from app.services.notificaciones.notification_service import NotificationService

        repo = AppointmentService._repo(db)
        row = repo.get_by_id(appointment_id)
        if row is None or row.doctor_id != doctor_id:
            raise HTTPException(status_code=404, detail="Cita no encontrada.")

        start_at = body.proposed_start_at
        end_at = start_at + timedelta(minutes=body.duration_minutes)
        row.appointment_date = start_at
        row.end_date = end_at
        row.status = "pending_patient_approval"
        repo.save(row)

        NotificationService(db).notify_user_push_in_app(
            row.patient_id,
            title="Propuesta de cita",
            message=f"El Dr. {doctor_name} ha asignado una fecha para tu consulta.",
            notification_type="appointment_proposed",
            payload={"appointment_id": str(row.id), "action": "patient_decision"},
            push_data={"type": "appointment_proposed", "appointment_id": str(row.id)},
        )
        if body.notes and body.notes.strip():
            from app.dto.timeline_dto import EventType
            from app.services.medical.doctor_timeline_note_service import (
                DoctorTimelineNoteService,
            )

            DoctorTimelineNoteService(db).save_note_for_event(
                doctor_id=doctor_id,
                patient_id=row.patient_id,
                timeline_event_id=f"appt_{row.id}",
                event_type=EventType.APPOINTMENT.value,
                content=body.notes.strip(),
            )
        return row

    @staticmethod
    def cancel_doctor_appointment(
        db: Session,
        appointment_id: UUID,
        doctor_id: UUID,
    ) -> Appointment:
        repo = AppointmentService._repo(db)
        appointment = repo.get_by_id(appointment_id)

        if not appointment:
            raise HTTPException(status_code=404, detail="Cita no encontrada")

        if appointment.doctor_id != doctor_id:
            raise HTTPException(
                status_code=403, detail="No tienes permiso para modificar esta cita"
            )

        if appointment.status == "canceled":
            raise HTTPException(
                status_code=400, detail="Esta cita ya se encuentra cancelada"
            )

        appointment.status = "canceled"
        return repo.save(appointment)

    @staticmethod
    def approve_doctor_approval(
        db: Session,
        appointment_id: UUID,
        doctor_id: UUID,
        doctor_name: str,
    ) -> Appointment:
        from app.services.notificaciones.notification_service import NotificationService

        repo = AppointmentService._repo(db)
        row = repo.get_by_id(appointment_id)
        if row is None or row.doctor_id != doctor_id:
            raise HTTPException(status_code=404, detail="Cita no encontrada.")
        if row.status != "pending_doctor_approval":
            raise HTTPException(
                status_code=400,
                detail="Esta cita no está pendiente de tu confirmación.",
            )
        row.status = "scheduled"
        repo.save(row)

        NotificationService(db).notify_user_push_in_app(
            row.patient_id,
            title="Cita confirmada",
            message=f"El Dr. {doctor_name} confirmó tu cita.",
            notification_type="appointment_confirmed",
            payload={"appointment_id": str(row.id)},
            push_data={
                "type": "appointment_confirmed",
                "appointment_id": str(row.id),
            },
        )
        AppointmentService._send_confirmed_email_to_patient(
            db,
            row,
            doctor_name=doctor_name,
            confirmed_from_web=True,
        )
        return row

    @staticmethod
    def reject_doctor_approval(
        db: Session,
        appointment_id: UUID,
        doctor_id: UUID,
        doctor_name: str,
    ) -> Appointment:
        from app.services.notificaciones.notification_service import NotificationService

        repo = AppointmentService._repo(db)
        row = repo.get_by_id(appointment_id)
        if row is None or row.doctor_id != doctor_id:
            raise HTTPException(status_code=404, detail="Cita no encontrada.")
        if row.status != "pending_doctor_approval":
            raise HTTPException(
                status_code=400,
                detail="Esta cita no está pendiente de tu confirmación.",
            )
        row.status = "canceled"
        repo.save(row)

        NotificationService(db).notify_user_push_in_app(
            row.patient_id,
            title="Cita no confirmada",
            message=f"El Dr. {doctor_name} no pudo confirmar la cita solicitada.",
            notification_type="appointment_rejected",
            payload={"appointment_id": str(row.id)},
            push_data={
                "type": "appointment_rejected",
                "appointment_id": str(row.id),
            },
        )
        AppointmentService._send_rejection_email_to_patient(
            db,
            row,
            doctor_name=doctor_name,
        )
        return row

    @staticmethod
    def doctor_reschedule_web_request(
        db: Session,
        appointment_id: UUID,
        doctor_id: UUID,
        doctor_name: str,
        body: AppointmentDoctorRescheduleRequest,
    ) -> Appointment:
        from app.repositories.appointment_response_token_repository import (
            AppointmentResponseTokenRepository,
        )

        repo = AppointmentService._repo(db)
        row = repo.get_by_id(appointment_id)
        if row is None or row.doctor_id != doctor_id:
            raise HTTPException(status_code=404, detail="Cita no encontrada.")
        if row.status not in ("pending_doctor_approval", "pending_patient_approval"):
            raise HTTPException(
                status_code=400,
                detail="Solo puedes reprogramar citas pendientes de confirmación.",
            )

        start_at = body.proposed_start_at
        end_at = start_at + timedelta(minutes=body.duration_minutes)
        row.appointment_date = start_at
        row.end_date = end_at
        row.status = "pending_patient_approval"
        repo.save(row)

        _, raw_token = AppointmentResponseTokenRepository(db).create_or_rotate(row.id)
        AppointmentService._notify_patient_proposal(
            db,
            row,
            doctor_name=doctor_name,
            raw_token=raw_token,
        )
        return row

    @staticmethod
    def doctor_reassign_canceled_appointment(
        db: Session,
        appointment_id: UUID,
        doctor_id: UUID,
        body: AppointmentDoctorProposeRequest,
        doctor_name: str,
    ) -> Appointment:
        repo = AppointmentService._repo(db)
        row = repo.get_by_id(appointment_id)
        if row is None or row.doctor_id != doctor_id:
            raise HTTPException(status_code=404, detail="Cita no encontrada.")
        if row.status != "canceled":
            raise HTTPException(
                status_code=400,
                detail="Solo puedes reasignar citas canceladas o rechazadas.",
            )

        start_at = body.proposed_start_at
        end_at = start_at + timedelta(minutes=body.duration_minutes)
        row.appointment_date = start_at
        row.end_date = end_at
        row.status = "scheduled"
        row.attendance_status = None
        repo.save(row)

        AppointmentService.notify_patient_doctor_scheduled(
            db,
            row,
            doctor_name=doctor_name,
        )
        return row

    @staticmethod
    def get_public_appointment_meta(
        db: Session, raw_token: str
    ) -> PublicAppointmentMetaResponse:
        from app.repositories.appointment_response_token_repository import (
            AppointmentResponseTokenRepository,
        )
        from app.services.medical.doctor_availability_service import (
            DoctorAvailabilityService,
        )
        from app.services.notificaciones.appointment_email_service import (
            _format_slot_range,
        )

        token_row, appt = AppointmentResponseTokenRepository(db).resolve(raw_token)
        settings = DoctorAvailabilityService.get_settings(db, appt.doctor_id)
        when_label = _format_slot_range(
            appt.appointment_date,
            appt.end_date,
            timezone=settings.timezone,
        )
        patient = appt.patient
        doctor = appt.doctor
        return PublicAppointmentMetaResponse(
            patient_name=(patient.name or "").strip() if patient else "Paciente",
            doctor_name=(doctor.name or "").strip() if doctor else "Tu médico",
            reason=(appt.reason or "").strip() or "Consulta médica",
            when_label=when_label,
            status=appt.status,
            already_responded=token_row.response_action is not None,
            response_action=token_row.response_action,
        )

    @staticmethod
    def respond_public_appointment(
        db: Session,
        raw_token: str,
        body: PublicAppointmentRespondRequest,
    ) -> PublicAppointmentRespondResponse:
        from app.repositories.appointment_response_token_repository import (
            AppointmentResponseTokenRepository,
        )
        from app.repositories.user_repository import UserRepository

        token_repo = AppointmentResponseTokenRepository(db)
        token_row, appt = token_repo.resolve(raw_token)

        if token_row.response_action is not None:
            raise HTTPException(
                status_code=409,
                detail="Esta cita ya fue respondida.",
            )
        if appt.status != "pending_patient_approval":
            raise HTTPException(
                status_code=400,
                detail="Esta cita ya no está pendiente de respuesta.",
            )

        doctor = UserRepository(db).get_by_id_with_role(appt.doctor_id)
        doctor_name = (doctor.name or "").strip() if doctor else "Tu médico"

        if body.action == "accept":
            appt.status = "scheduled"
            AppointmentService._repo(db).save(appt)
            token_repo.mark_responded(token_row, "accept")
            AppointmentService._send_confirmed_email_to_patient(
                db,
                appt,
                doctor_name=doctor_name,
                confirmed_from_web=True,
            )
            return PublicAppointmentRespondResponse(
                status=appt.status,
                message="Cita confirmada. Revisa tu correo con los detalles.",
            )

        appt.status = "canceled"
        AppointmentService._repo(db).save(appt)
        token_repo.mark_responded(token_row, "reject")
        return PublicAppointmentRespondResponse(
            status=appt.status,
            message="Cita rechazada.",
        )