from sqlalchemy.orm import Session
from datetime import datetime
# Importaciones corregidas según tu estructura:
from app.models.user import User as UserModel
from app.models.appointment import Appointment

class PatientRepository:
    def get_timeline_events(self, db: Session, patient_id: str):
        all_events = []

        # 1. Evento: Registro de Cuenta (Bienvenida)
        patient = db.query(UserModel).filter(UserModel.id == patient_id).first()
        if patient:
            all_events.append({
                "id": str(patient.id),
                "date": patient.created_at.strftime("%d %b %Y"),
                "time": patient.created_at.strftime("%I:%M %p"),
                "title": "Bienvenido a Keepi",
                "actor": "Sistema",
                "event_type": "registration",
                "description": "Se ha creado tu expediente digital",
                "raw_dt": patient.created_at
            })

        # 2. Evento: Citas Médicas
        appointments = db.query(Appointment).filter(Appointment.patient_id == patient_id).all()
        for appt in appointments:
            # Usamos appointment_date que es el campo que tienes en tu modelo
            dt_combined = appt.appointment_date
            all_events.append({
                "id": str(appt.id),
                "date": dt_combined.strftime("%d %b %Y"),
                "time": dt_combined.strftime("%I:%M %p"),
                "title": f"Cita: {appt.reason}",
                "actor": "Tu Médico",
                "event_type": "appointment",
                "description": appt.status,
                "raw_dt": dt_combined
            })

        # 3. Ordenar todo por fecha (Lo más nuevo arriba)
        all_events.sort(key=lambda x: x['raw_dt'], reverse=True)

        return all_events