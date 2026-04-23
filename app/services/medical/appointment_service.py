from datetime import timedelta
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID

from app.models.appointment import Appointment
# Asegúrate de importar los DTOs que creamos en el paso anterior (ajusta la ruta si es necesario)
from app.models.appointment import (
    AppointmentPatientCreateRequest,
    AppointmentDoctorProposeRequest,
    AppointmentPatientRespondRequest
)

class AppointmentService:
    
    # PASO 1: El paciente envía la solicitud (Solo motivo)
    @staticmethod
    def create_patient_request(db: Session, patient_id: str, request_data: AppointmentPatientCreateRequest) -> Appointment:
        new_appointment = Appointment(
            patient_id=patient_id,
            doctor_id=request_data.doctor_id,
            reason=request_data.reason,
            status="pending_doctor_proposal" # Estado inicial
        )
        db.add(new_appointment)
        db.commit()
        db.refresh(new_appointment)
        
        # Aquí a futuro podrías llamar a tu servicio de notificaciones para avisarle al doctor
        return new_appointment

    # PASO 2: El doctor propone un horario
    @staticmethod
    def propose_doctor_time(db: Session, appointment_id: str, doctor_id: str, proposal_data: AppointmentDoctorProposeRequest) -> Appointment:
        appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
        
        if not appointment:
            raise HTTPException(status_code=404, detail="Cita no encontrada")
            
        # Validar que el doctor sea el dueño de esta cita y que esté en el estado correcto
        if str(appointment.doctor_id) != doctor_id:
            raise HTTPException(status_code=403, detail="No tienes permiso para modificar esta cita")
            
        if appointment.status != "pending_doctor_proposal":
            raise HTTPException(status_code=400, detail="Esta cita no está esperando propuesta")

        # Asignamos las fechas y cambiamos el estado
        appointment.appointment_date = proposal_data.proposed_start_at
        appointment.end_date = proposal_data.proposed_start_at + timedelta(minutes=proposal_data.duration_minutes)
        appointment.status = "pending_patient_approval" # Cambia de estado
        
        # Si enviaste un campo de notas en el modelo, lo guardamos aquí
        # appointment.notes = proposal_data.notes 
        
        db.commit()
        db.refresh(appointment)
        
        # Aquí a futuro disparas la notificación push (campanita) para el paciente
        return appointment

    # PASO 3: El paciente acepta o rechaza
    @staticmethod
    def respond_to_proposal(db: Session, appointment_id: str, patient_id: str, response_data: AppointmentPatientRespondRequest) -> Appointment:
        appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
        
        if not appointment:
            raise HTTPException(status_code=404, detail="Cita no encontrada")
            
        if str(appointment.patient_id) != patient_id:
            raise HTTPException(status_code=403, detail="No tienes permiso para modificar esta cita")
            
        if appointment.status != "pending_patient_approval":
            raise HTTPException(status_code=400, detail="Esta cita no tiene una propuesta pendiente")

        # Aplicamos la decisión del paciente
        if response_data.action == "accept":
            appointment.status = "scheduled"
        elif response_data.action == "reject":
            appointment.status = "canceled"
            # Como mencionaste: si rechaza, se cancela y debe empezar de nuevo. 
            # No borramos el registro para tener historial, solo lo cancelamos.

        db.commit()
        db.refresh(appointment)
        
        # Aquí notificas al doctor si fue aceptada o rechazada
        return appointment