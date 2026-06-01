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

        return repo.save(appointment)

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