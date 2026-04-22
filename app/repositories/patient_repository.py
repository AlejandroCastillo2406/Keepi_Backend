from sqlalchemy.orm import Session
from app.models.user import User as UserModel
from app.models.appointment import Appointment
from app.models.prescription import Prescription
from app.models.analysis_request import AnalysisRequest

class PatientRepository:
    def get_timeline_events(self, db: Session, patient_id: str):
        all_events = []

        # 1. REGISTRO
        try:
            p = db.query(UserModel).filter(UserModel.id == patient_id).first()
            if p and p.created_at:
                all_events.append({
                    "id": f"reg_{p.id}",
                    "date": p.created_at.strftime("%d %b %Y"),
                    "time": p.created_at.strftime("%I:%M %p"),
                    "title": "Bienvenido a Keepi",
                    "actor": "Sistema",
                    "event_type": "registration",
                    "raw_dt": p.created_at
                })
        except Exception: pass

        # 2. CITAS
        try:
            appts = db.query(Appointment).filter(Appointment.patient_id == patient_id).all()
            for a in appts:
                all_events.append({
                    "id": f"appt_{a.id}",
                    "date": a.appointment_date.strftime("%d %b %Y"),
                    "time": a.appointment_date.strftime("%I:%M %p"),
                    "title": f"Cita: {a.reason}",
                    "actor": "Médico",
                    "event_type": "appointment",
                    "raw_dt": a.appointment_date
                })
        except Exception: pass

        # 3. RECETAS
        try:
            prescs = db.query(Prescription).filter(Prescription.patient_id == patient_id).all()
            for pr in prescs:
                all_events.append({
                    "id": f"pres_{pr.id}",
                    "date": pr.created_at.strftime("%d %b %Y"),
                    "time": pr.created_at.strftime("%I:%M %p"),
                    "title": "Receta Médica",
                    "actor": "Médico",
                    "event_type": "prescription",
                    "raw_dt": pr.created_at
                })
        except Exception: pass

        # 4. ANÁLISIS (Usa tu tabla analysis_requests)
        try:
            # Consultamos tu modelo AnalysisRequest
            requests = db.query(AnalysisRequest).filter(AnalysisRequest.patient_id == patient_id).all()
            for req in requests:
                # Evento Solicitud
                if req.created_at:
                    all_events.append({
                        "id": f"asig_{req.id}",
                        "date": req.created_at.strftime("%d %b %Y"),
                        "time": req.created_at.strftime("%I:%M %p"),
                        "title": f"Análisis solicitado: {req.description}",
                        "actor": "Médico",
                        "event_type": "analysis",
                        "raw_dt": req.created_at
                    })
                # Evento Resultado
                if req.completed_at:
                    all_events.append({
                        "id": f"comp_{req.id}",
                        "date": req.completed_at.strftime("%d %b %Y"),
                        "time": req.completed_at.strftime("%I:%M %p"),
                        "title": f"Resultado disponible: {req.description}",
                        "actor": "Paciente",
                        "event_type": "analysis",
                        "raw_dt": req.completed_at
                    })
        except Exception as e:
            print(f"DEBUG: Error en bloque análisis: {e}")

        all_events.sort(key=lambda x: x['raw_dt'], reverse=True)
        return all_events