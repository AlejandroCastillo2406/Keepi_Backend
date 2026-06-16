from datetime import datetime, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.appointment import (
    Appointment,
    AppointmentCreateRequest,
    AppointmentDoctorProposeRequest,
    AppointmentPatientCreateRequest,
    AppointmentPatientRespondRequest,
)
from app.repositories.appointment_repository import AppointmentRepository


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
        from app.models.appointment_response_token import AppointmentPatientResponseToken

        token_repo = AppointmentService._token_repo(db)
        token = (
            token_repo._db.query(AppointmentPatientResponseToken)
            .filter(AppointmentPatientResponseToken.appointment_id == saved.id)
            .first()
        )
        if token is not None and token.response_action is None:
            token_repo.mark_responded(token, response_data.action)
        AppointmentService._notify_doctor_patient_response(
            db, saved, response_data.action
        )
        return saved

    @staticmethod
    def _notify_doctor_patient_response(
        db: Session, appointment: Appointment, action: str
    ) -> None:
        from app.repositories.user_repository import UserRepository
        from app.services.notificaciones.notification_service import NotificationService

        users = UserRepository(db)
        patient = users.get_by_id_plain(appointment.patient_id)
        patient_name = (patient.name if patient else "") or "Paciente"
        when_label = AppointmentService._format_appointment_when(
            appointment.appointment_date, appointment.end_date
        )
        notifier = NotificationService(db)
        if action == "accept":
            notifier.notify_user_push_in_app(
                appointment.doctor_id,
                title="Cita confirmada",
                message=f"{patient_name} confirmó la cita del {when_label}.",
                notification_type="appointment_confirmed",
                payload={"appointment_id": str(appointment.id)},
                push_data={
                    "type": "appointment_confirmed",
                    "appointment_id": str(appointment.id),
                },
            )
        else:
            notifier.notify_user_push_in_app(
                appointment.doctor_id,
                title="Cita cancelada",
                message=f"{patient_name} canceló la cita del {when_label}.",
                notification_type="appointment_rejected",
                payload={"appointment_id": str(appointment.id)},
                push_data={
                    "type": "appointment_rejected",
                    "appointment_id": str(appointment.id),
                },
            )

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
            status="pending_patient_approval",
            reason=body.reason.strip() or "Consulta médica",
        )
        return AppointmentService._repo(db).add(row)

    @staticmethod
    def _token_repo(db: Session):
        from app.repositories.appointment_response_token_repository import (
            AppointmentResponseTokenRepository,
        )

        return AppointmentResponseTokenRepository(db)

    @staticmethod
    def _format_appointment_when(start_at: datetime | None, end_at: datetime | None) -> str:
        if start_at is None:
            return "Por confirmar"
        local = start_at.astimezone()
        date_part = local.strftime("%d/%m/%Y")
        start_part = local.strftime("%H:%M")
        if end_at is not None:
            end_local = end_at.astimezone()
            end_part = end_local.strftime("%H:%M")
            return f"{date_part} · {start_part} – {end_part}"
        return f"{date_part} · {start_part}"

    @staticmethod
    def notify_patient_appointment_proposal(
        db: Session,
        appointment_id: UUID,
        doctor_name: str,
    ) -> None:
        import logging

        from app.repositories.user_repository import UserRepository
        from app.services.notificaciones.appointment_confirm_email_service import (
            build_public_appointment_response_link,
            send_appointment_confirm_email,
        )
        from app.services.notificaciones.notification_service import NotificationService

        log = logging.getLogger(__name__)
        repo = AppointmentService._repo(db)
        row = repo.get_by_id(appointment_id)
        if row is None:
            return

        users = UserRepository(db)
        patient = users.get_by_id_plain(row.patient_id)
        patient_email = (patient.email if patient else "") or ""
        patient_name = (patient.name if patient else "") or "Paciente"
        when_label = AppointmentService._format_appointment_when(
            row.appointment_date, row.end_date
        )

        _, raw_token = AppointmentService._token_repo(db).create_or_refresh(row.id)
        confirm_link = build_public_appointment_response_link(raw_token, "accept")
        cancel_link = build_public_appointment_response_link(raw_token, "reject")

        NotificationService(db).notify_user_push_in_app(
            row.patient_id,
            title="Confirma tu cita",
            message=f"El Dr. {doctor_name} te propuso una cita para {when_label}.",
            notification_type="appointment_proposed",
            payload={"appointment_id": str(row.id), "action": "patient_decision"},
            push_data={"type": "appointment_proposed", "appointment_id": str(row.id)},
        )

        if not patient_email.strip():
            log.warning(
                "Cita %s: paciente sin correo; no se envió email de confirmación",
                row.id,
            )
            return

        result = send_appointment_confirm_email(
            to_email=patient_email,
            patient_name=patient_name,
            doctor_name=doctor_name,
            reason=row.reason or "",
            when_label=when_label,
            confirm_link=confirm_link,
            cancel_link=cancel_link,
        )
        if not result.success:
            log.warning(
                "Cita %s: no se pudo enviar email de confirmación: %s",
                row.id,
                result.error,
            )

    @staticmethod
    def get_public_appointment_meta(db: Session, raw_token: str):
        from app.models.appointment import PublicAppointmentMetaResponse
        from app.repositories.user_repository import UserRepository

        token_row = AppointmentService._token_repo(db).get_by_raw_token(raw_token)
        if token_row is None:
            raise HTTPException(status_code=404, detail="Enlace no válido o expirado.")

        row = AppointmentService._repo(db).get_by_id(token_row.appointment_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Cita no encontrada.")

        users = UserRepository(db)
        doctor = users.get_by_id_plain(row.doctor_id)
        patient = users.get_by_id_plain(row.patient_id)
        doctor_name = (doctor.name if doctor else "") or "Tu médico"
        patient_name = (patient.name if patient else "") or "Paciente"

        can_respond = (
            row.status == "pending_patient_approval"
            and token_row.response_action is None
        )
        message = None
        if token_row.response_action == "accept" or row.status == "scheduled":
            message = "Ya confirmaste esta cita."
        elif token_row.response_action == "reject" or row.status == "canceled":
            message = "Esta cita fue cancelada."
        elif row.status != "pending_patient_approval":
            message = "Esta cita ya no requiere confirmación."

        return PublicAppointmentMetaResponse(
            doctor_name=doctor_name,
            patient_name=patient_name,
            reason=row.reason or "",
            appointment_date=row.appointment_date,
            end_date=row.end_date,
            status=row.status,
            response_action=token_row.response_action,
            can_respond=can_respond,
            message=message,
        )

    @staticmethod
    def respond_public_appointment(db: Session, raw_token: str, action: str):
        from app.models.appointment import PublicAppointmentRespondResponse
        from app.repositories.user_repository import UserRepository
        from app.services.notificaciones.notification_service import NotificationService

        token_row = AppointmentService._token_repo(db).get_by_raw_token(raw_token)
        if token_row is None:
            raise HTTPException(status_code=404, detail="Enlace no válido o expirado.")

        repo = AppointmentService._repo(db)
        row = repo.get_by_id(token_row.appointment_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Cita no encontrada.")

        if token_row.response_action is not None:
            if token_row.response_action == action:
                msg = (
                    "Tu cita quedó confirmada."
                    if action == "accept"
                    else "Tu cita quedó cancelada."
                )
                return PublicAppointmentRespondResponse(
                    status=row.status,
                    action=token_row.response_action,
                    message=msg,
                )
            raise HTTPException(
                status_code=409,
                detail="Esta cita ya fue respondida anteriormente.",
            )

        if row.status != "pending_patient_approval":
            raise HTTPException(
                status_code=400,
                detail="Esta cita ya no está pendiente de confirmación.",
            )

        if action == "accept":
            row.status = "scheduled"
            message = "Gracias. Tu cita quedó confirmada."
        else:
            row.status = "canceled"
            message = "Tu cita quedó cancelada."

        repo.save(row)
        AppointmentService._token_repo(db).mark_responded(token_row, action)

        users = UserRepository(db)
        patient = users.get_by_id_plain(row.patient_id)
        patient_name = (patient.name if patient else "") or "Paciente"
        when_label = AppointmentService._format_appointment_when(
            row.appointment_date, row.end_date
        )

        if action == "accept":
            NotificationService(db).notify_user_push_in_app(
                row.doctor_id,
                title="Cita confirmada",
                message=f"{patient_name} confirmó la cita del {when_label}.",
                notification_type="appointment_confirmed",
                payload={"appointment_id": str(row.id)},
                push_data={
                    "type": "appointment_confirmed",
                    "appointment_id": str(row.id),
                },
            )
        else:
            NotificationService(db).notify_user_push_in_app(
                row.doctor_id,
                title="Cita cancelada",
                message=f"{patient_name} canceló la cita del {when_label}.",
                notification_type="appointment_rejected",
                payload={"appointment_id": str(row.id)},
                push_data={
                    "type": "appointment_rejected",
                    "appointment_id": str(row.id),
                },
            )

        return PublicAppointmentRespondResponse(
            status=row.status,
            action=action,
            message=message,
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

        AppointmentService.notify_patient_appointment_proposal(
            db, row.id, doctor_name
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
        return row