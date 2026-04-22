from sqlalchemy.orm import Session
from app.models.user import User as UserModel
from app.models.appointment import Appointment
from app.models.prescription import Prescription
from app.models.document import Document

class PatientRepository:
    def get_timeline_events(self, db: Session, patient_id: str):
        all_events = []

        # 1. REGISTRO (Bienvenida)
        try:
            patient = db.query(UserModel).filter(UserModel.id == patient_id).first()
            if patient:
                all_events.append({
                    "id": str(patient.id),
                    "date": patient.created_at.strftime("%d %b %Y"),
                    "time": patient.created_at.strftime("%I:%M %p"),
                    "title": "Bienvenido a Keepi",
                    "actor": "Sistema",
                    "event_type": "registration",
                    "raw_dt": patient.created_at
                })
        except Exception: pass

        # 2. CITAS MÉDICAS
        try:
            appts = db.query(Appointment).filter(Appointment.patient_id == patient_id).all()
            for a in appts:
                # Usamos appointment_date porque es tu campo en la DB
                all_events.append({
                    "id": str(a.id),
                    "date": a.appointment_date.strftime("%d %b %Y"),
                    "time": a.appointment_date.strftime("%I:%M %p"),
                    "title": f"Cita: {a.reason}",
                    "actor": "Médico",
                    "event_type": "appointment",
                    "raw_dt": a.appointment_date
                })
        except Exception: pass

        # 3. RECETAS ASIGNADAS
        try:
            prescriptions = db.query(Prescription).filter(Prescription.patient_id == patient_id).all()
            for p in prescriptions:
                all_events.append({
                    "id": str(p.id),
                    "date": p.created_at.strftime("%d %b %Y"),
                    "time": p.created_at.strftime("%I:%M %p"),
                    "title": "Receta Médica",
                    "actor": "Médico",
                    "event_type": "prescription",
                    "raw_dt": p.created_at
                })
        except Exception: pass

        # 4. ANÁLISIS / DOCUMENTOS SUBIDOS
        try:
            docs = db.query(Document).filter(Document.patient_id == patient_id).all()
            for d in docs:
                all_events.append({
                    "id": str(d.id),
                    "date": d.created_at.strftime("%d %b %Y"),
                    "time": d.created_at.strftime("%I:%M %p"),
                    "title": f"Estudio: {d.name}",
                    "actor": "Paciente",
                    "event_type": "analysis",
                    "raw_dt": d.created_at
                })
        except Exception: pass

        # ORDENAR TODO: De más reciente a más antiguo
        all_events.sort(key=lambda x: x['raw_dt'], reverse=True)
        return all_events