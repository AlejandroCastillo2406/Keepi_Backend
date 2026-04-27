import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

# Importaciones de DTOs
from app.dto.timeline_dto import EventType, TimelineEventResponse, QuestionnaireStatus

# Importaciones de Modelos
from app.models.analysis_request import AnalysisRequest
from app.models.appointment import Appointment
from app.models.prescription import Prescription
from app.models.user import User as UserModel
from app.models.questionnaire_invitation import QuestionnaireInvitation 

logger = logging.getLogger(__name__)

_MES = (
    "ene", "feb", "mar", "abr", "may", "jun",
    "jul", "ago", "sep", "oct", "nov", "dic",
)

def _as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def _fmt_date(dt: datetime) -> str:
    dt = _as_utc(dt) or dt
    return f"{dt.day} {_MES[dt.month - 1].capitalize()} {dt.year}"

def _fmt_time(dt: datetime) -> str:
    dt = _as_utc(dt) or dt
    h12 = dt.hour % 12 or 12
    ampm = "AM" if dt.hour < 12 else "PM"
    return f"{h12:02d}:{dt.minute:02d} {ampm}"

def _user_name(db: Session, user_id) -> Optional[str]:
    if user_id is None:
        return None
    u = db.query(UserModel).filter(UserModel.id == user_id).first()
    return u.name if u else None

class PatientRepository:
    def get_timeline_events(self, db: Session, patient_id: str) -> List[TimelineEventResponse]:
        try:
            pid = UUID(str(patient_id))
        except (ValueError, TypeError):
            logger.warning("patient_id inválido para timeline: %s", patient_id)
            return []

        raw_events: List[Dict[str, Any]] = []

        # --- 1. Cuenta / registro ---
        try:
            p = db.query(UserModel).filter(UserModel.id == pid).first()
            if p and p.created_at:
                creator = _user_name(db, p.created_by_user_id)
                subtitle = "Alta clínica en la plataforma (invitación de tu médico)" if creator else "Te registraste en Keepi"
                raw_events.append({
                    "id": f"reg_{p.id}",
                    "date": _fmt_date(p.created_at),
                    "time": _fmt_time(p.created_at),
                    "title": "Cuenta creada en Keepi",
                    "actor": "Sistema",
                    "event_type": EventType.REGISTRATION,
                    "subtitle": subtitle,
                    "description": subtitle,
                    "raw_dt": _as_utc(p.created_at),
                })
        except Exception as e:
            db.rollback() # Libera la transacción en caso de error
            logger.error(f"Error en timeline (registro): {e}")

        # --- 2. Citas ---
        try:
            appts = db.query(Appointment).filter(Appointment.patient_id == pid).all()
            for a in appts:
                when = _as_utc(a.appointment_date)
                if not when: continue
                raw_events.append({
                    "id": f"appt_{a.id}",
                    "date": _fmt_date(when),
                    "time": _fmt_time(when),
                    "title": "Cita médica",
                    "actor": "Doctor",
                    "event_type": EventType.APPOINTMENT,
                    "subtitle": (a.reason or "").strip() or "Consulta",
                    "description": (a.reason or "").strip() or "Consulta",
                    "raw_dt": when,
                })
        except Exception as e:
            db.rollback()
            logger.error(f"Error en timeline (citas): {e}")

        # --- 3. Recetas ---
        try:
            prescs = db.query(Prescription).filter(Prescription.patient_id == pid).all()
            for pr in prescs:
                if not pr.created_at: continue
                when = _as_utc(pr.created_at)
                raw_events.append(
                    {
                        "id": f"pres_{pr.id}",
                        "date": _fmt_date(when),
                        "time": _fmt_time(when),
                        "title": "Receta médica",
                        "actor": "Doctor",
                        "event_type": EventType.PRESCRIPTION,
                        "subtitle": "Receta registrada en tu historial",
                        "description": "Receta registrada en tu historial",
                        "raw_dt": when,
                    }
                )
        except Exception as e:
            db.rollback()
            logger.error(f"Error en timeline (recetas): {e}")

        # --- 4. Solicitudes de análisis + subida de documento ---
        try:
            requests = db.query(AnalysisRequest).filter(AnalysisRequest.patient_id == pid).order_by(AnalysisRequest.created_at.asc()).all()
            for req in requests:
                desc = (req.description or "").strip() or "Estudio solicitado"
                if req.created_at:
                    when = _as_utc(req.created_at)
                    raw_events.append({
                        "id": f"anreq_{req.id}",
                        "date": _fmt_date(when),
                        "time": _fmt_time(when),
                        "title": "Análisis solicitado por tu médico",
                        "actor": "Doctor",
                        "event_type": EventType.ANALYSIS_REQUEST,
                        "subtitle": desc,
                        "description": desc,
                        "raw_dt": when,
                        "analysis_request_id": req.id,
                    })
                if req.document_id and req.completed_at:
                    when_u = _as_utc(req.completed_at)
                    raw_events.append({
                        "id": f"anupl_{req.id}",
                        "date": _fmt_date(when_u),
                        "time": _fmt_time(when_u),
                        "title": "Estudio subido",
                        "actor": "Paciente",
                        "event_type": EventType.ANALYSIS_UPLOAD,
                        "subtitle": f" Archivo vinculado a la solicitud de {desc}",
                        "description": f"Archivo vinculado a la solicitud de {desc}",
                        "raw_dt": when_u,
                        "analysis_request_id": None,
                    })
        except Exception as e:
            db.rollback()
            logger.error(f"Error en timeline (análisis): {e}")

        # --- 5. Cuestionarios ---
        now_utc = datetime.now(timezone.utc)
        try:
            invitations = db.query(QuestionnaireInvitation).filter(QuestionnaireInvitation.patient_id == pid).all()
            for inv in invitations:
                when_sent = _as_utc(inv.created_at)
                if not when_sent: continue

                q_status = None
                completed_time = None

                if inv.status == "complete":
                    q_status = QuestionnaireStatus.COMPLETED
                    if inv.completed_at:
                        completed_time = _as_utc(inv.completed_at).isoformat()
                else: 
                    expires_utc = _as_utc(inv.expires_at)
                    if expires_utc and expires_utc < now_utc:
                        q_status = QuestionnaireStatus.UNANSWERED
                    else:
                        q_status = QuestionnaireStatus.PENDING

                raw_events.append({
                    "id": f"quest_{inv.id}",
                    "date": _fmt_date(when_sent),
                    "time": _fmt_time(when_sent),
                    "title": "Cuestionario médico",
                    "actor": "Doctor",
                    "event_type": EventType.QUESTIONNAIRE,
                    "subtitle": "Cuestionario de seguimiento",
                    "description": "Se te envió un cuestionario médico para contestar.",
                    "raw_dt": when_sent,
                    "questionnaire_status": q_status,
                    "completed_at": completed_time,
                })
        except Exception as e:
            db.rollback()
            # Este es el log que nos dirá la verdad sobre por qué falló el modelo
            logger.error(f"Error en timeline (cuestionarios): {e}")

        # --- ORDENAMIENTO ---
        raw_events.sort(key=lambda x: x["raw_dt"])

        pending_request_ids = set()
        try:
            pending_rows = db.query(AnalysisRequest).filter(
                AnalysisRequest.patient_id == pid,
                AnalysisRequest.status == "pending",
                AnalysisRequest.document_id.is_(None),
            ).all()
            pending_request_ids = {r.id for r in pending_rows}
        except Exception as e:
            db.rollback()
            logger.error(f"Error en timeline (pending rows): {e}")

        out: List[TimelineEventResponse] = []
        for e in raw_events:
            rid = e.get("analysis_request_id")
            if e["raw_dt"] > now_utc:
                vstate = "future"
            elif rid and rid in pending_request_ids:
                vstate = "current"
            else:
                vstate = "completed"

            out.append(
                TimelineEventResponse(
                    id=e["id"],
                    date=e["date"],
                    time=e.get("time"),
                    title=e["title"],
                    actor=e["actor"],
                    event_type=e["event_type"],
                    subtitle=e.get("subtitle"),
                    description=e.get("description") or (e.get("subtitle") or ""),
                    occurred_at=e["raw_dt"].isoformat(),
                    visual_state=vstate,
                    questionnaire_status=e.get("questionnaire_status"),  
                    completed_at=e.get("completed_at"),  
                )
            )

        return out