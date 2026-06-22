import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session


from app.dto.timeline_dto import EventType, TimelineEventResponse, QuestionnaireStatus


from app.models.analysis_request import AnalysisRequest
from app.models.appointment import Appointment
from app.models.document import Document
from app.models.prescription import Prescription
from app.models.user import User as UserModel
from app.models.questionnaire_invitation import (
    QuestionnaireInvitation,
    QuestionnaireInvitationItem,
)

logger = logging.getLogger(__name__)

_MES = (
    "ene",
    "feb",
    "mar",
    "abr",
    "may",
    "jun",
    "jul",
    "ago",
    "sep",
    "oct",
    "nov",
    "dic",
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


def _invitation_timeline_label(
    inv: QuestionnaireInvitation, db: Session
) -> str:
    parts: List[str] = []
    item_count = (
        db.query(QuestionnaireInvitationItem)
        .filter(QuestionnaireInvitationItem.invitation_id == inv.id)
        .count()
    )
    if bool(getattr(inv, "enable_clinical_intake", False)):
        parts.append("Ficha clínica")
    if item_count > 0:
        row = (
            db.query(QuestionnaireInvitationItem.template_name_snapshot)
            .filter(QuestionnaireInvitationItem.invitation_id == inv.id)
            .order_by(QuestionnaireInvitationItem.sort_order.asc())
            .first()
        )
        name = ((row[0] if row else "") or "").strip() or "Cuestionario"
        parts.append(name)
    if bool(getattr(inv, "collect_prior_documents", False)):
        parts.append("Documentos previos")
    return " · ".join(parts) if parts else "Solicitud clínica"


def _prior_documents_for_patient(db: Session, pid: UUID) -> List[Document]:
    patient_tag = f"patient:{pid}"
    rows = (
        db.query(Document)
        .filter(Document.tags.isnot(None))
        .order_by(Document.created_at.desc())
        .all()
    )
    return [
        d
        for d in rows
        if d.tags and "documento_previo" in d.tags and patient_tag in d.tags
    ]


class PatientRepository:
    def get_timeline_events(
        self, db: Session, patient_id: str
    ) -> List[TimelineEventResponse]:
        try:
            pid = UUID(str(patient_id))
        except (ValueError, TypeError):
            logger.warning("patient_id inválido para timeline: %s", patient_id)
            return []

        raw_events: List[Dict[str, Any]] = []

        try:
            p = db.query(UserModel).filter(UserModel.id == pid).first()
            if p and p.created_at:
                creator = _user_name(db, p.created_by_user_id)
                subtitle = (
                    "Alta clínica en la plataforma (invitación de tu médico)"
                    if creator
                    else "Te registraste en Keepi"
                )
                raw_events.append(
                    {
                        "id": f"reg_{p.id}",
                        "date": _fmt_date(p.created_at),
                        "time": _fmt_time(p.created_at),
                        "title": "Cuenta creada en Keepi",
                        "actor": "Sistema",
                        "event_type": EventType.REGISTRATION,
                        "subtitle": subtitle,
                        "description": subtitle,
                        "raw_dt": _as_utc(p.created_at),
                    }
                )
        except Exception as e:
            db.rollback()
            logger.error(f"Error en timeline (registro): {e}")

        try:
            appts = db.query(Appointment).filter(Appointment.patient_id == pid).all()
            for a in appts:
                when = _as_utc(a.appointment_date)
                if not when:
                    continue
                raw_events.append(
                    {
                        "id": f"appt_{a.id}",
                        "date": _fmt_date(when),
                        "time": _fmt_time(when),
                        "title": "Cita médica",
                        "actor": "Doctor",
                        "event_type": EventType.APPOINTMENT,
                        "subtitle": (a.reason or "").strip() or "Consulta",
                        "description": (a.reason or "").strip() or "Consulta",
                        "raw_dt": when,
                    }
                )
        except Exception as e:
            db.rollback()
            logger.error(f"Error en timeline (citas): {e}")

        try:
            prescs = db.query(Prescription).filter(Prescription.patient_id == pid).all()
            for pr in prescs:
                if not pr.created_at:
                    continue
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

        try:
            requests = (
                db.query(AnalysisRequest)
                .filter(AnalysisRequest.patient_id == pid)
                .order_by(AnalysisRequest.created_at.asc())
                .all()
            )
            for req in requests:
                desc = (req.description or "").strip() or "Estudio solicitado"
                if req.created_at:
                    when = _as_utc(req.created_at)
                    raw_events.append(
                        {
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
                        }
                    )
                if req.document_id and req.completed_at:
                    when_u = _as_utc(req.completed_at)
                    raw_events.append(
                        {
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
                        }
                    )
        except Exception as e:
            db.rollback()
            logger.error(f"Error en timeline (análisis): {e}")

        now_utc = datetime.now(timezone.utc)
        prior_for_patient: List[Document] = []
        try:
            prior_for_patient = _prior_documents_for_patient(db, pid)
            for doc in prior_for_patient:
                when = _as_utc(doc.created_at) or now_utc
                doc_name = (doc.name or doc.file_name or "Documento").strip()
                raw_events.append(
                    {
                        "id": f"priordoc_{doc.id}",
                        "date": _fmt_date(when),
                        "time": _fmt_time(when),
                        "title": "Documento previo subido",
                        "actor": "Paciente",
                        "event_type": EventType.PRIOR_DOCUMENTS,
                        "subtitle": doc_name,
                        "description": (
                            "Estudio o informe médico previo compartido con tu médico."
                        ),
                        "raw_dt": when,
                        "action_patient_id": str(pid),
                        "prior_documents_count": 1,
                    }
                )
        except Exception as e:
            db.rollback()
            logger.error(f"Error en timeline (documentos previos): {e}")

        try:
            invitations = (
                db.query(QuestionnaireInvitation)
                .filter(QuestionnaireInvitation.patient_id == pid)
                .all()
            )
            for inv in invitations:
                when_sent = _as_utc(inv.created_at)
                if not when_sent:
                    continue

                label = _invitation_timeline_label(inv, db)
                enable_intake = bool(getattr(inv, "enable_clinical_intake", False))
                collect_prior = bool(getattr(inv, "collect_prior_documents", False))
                intake_done_at = _as_utc(getattr(inv, "intake_completed_at", None))
                expires_utc = _as_utc(inv.expires_at)
                is_active_pending = inv.status == "pending" and (
                    expires_utc is None or expires_utc >= now_utc
                )
                inv_tag = f"questionnaire_invitation:{inv.id}"
                prior_docs_for_inv = sum(
                    1
                    for d in prior_for_patient
                    if d.tags and inv_tag in d.tags
                )

                if enable_intake:
                    if intake_done_at:
                        answered_by = (
                            getattr(inv, "questionnaire_answered_by", None) or "patient"
                        )
                        actor = "Doctor" if answered_by == "doctor" else "Paciente"
                        raw_events.append(
                            {
                                "id": f"intake_{inv.id}",
                                "date": _fmt_date(intake_done_at),
                                "time": _fmt_time(intake_done_at),
                                "title": "Ficha clínica completada",
                                "actor": actor,
                                "event_type": EventType.CLINICAL_INTAKE,
                                "subtitle": label,
                                "description": (
                                    "Ficha clínica previa a la consulta completada "
                                    "(datos, antecedentes, alergias y medicamentos)."
                                ),
                                "raw_dt": intake_done_at,
                                "action_patient_id": str(pid),
                            }
                        )
                    elif is_active_pending:
                        raw_events.append(
                            {
                                "id": f"intake_req_{inv.id}",
                                "date": _fmt_date(when_sent),
                                "time": _fmt_time(when_sent),
                                "title": "Ficha clínica solicitada",
                                "actor": "Doctor",
                                "event_type": EventType.CLINICAL_INTAKE,
                                "subtitle": label,
                                "description": (
                                    "Tu médico te envió una ficha clínica para completar."
                                ),
                                "raw_dt": when_sent,
                                "force_visual_state": "current",
                                "action_patient_id": str(pid),
                            }
                        )

                if collect_prior:
                    if is_active_pending and prior_docs_for_inv == 0:
                        raw_events.append(
                            {
                                "id": f"priordocs_req_{inv.id}",
                                "date": _fmt_date(when_sent),
                                "time": _fmt_time(when_sent),
                                "title": "Documentos previos solicitados",
                                "actor": "Doctor",
                                "event_type": EventType.PRIOR_DOCUMENTS,
                                "subtitle": label,
                                "description": (
                                    "Tu médico solicitó estudios o informes médicos previos."
                                ),
                                "raw_dt": when_sent,
                                "force_visual_state": "current",
                                "action_patient_id": str(pid),
                            }
                        )
                    elif prior_docs_for_inv > 0:
                        raw_events.append(
                            {
                                "id": f"priordocs_sent_{inv.id}",
                                "date": _fmt_date(when_sent),
                                "time": _fmt_time(when_sent),
                                "title": "Documentos previos solicitados",
                                "actor": "Doctor",
                                "event_type": EventType.PRIOR_DOCUMENTS,
                                "subtitle": (
                                    f"{prior_docs_for_inv} archivo subido"
                                    if prior_docs_for_inv == 1
                                    else f"{prior_docs_for_inv} archivos subidos"
                                ),
                                "description": (
                                    "Solicitud de documentos previos vinculada a una "
                                    "invitación clínica."
                                ),
                                "raw_dt": when_sent,
                                "action_patient_id": str(pid),
                                "prior_documents_count": prior_docs_for_inv,
                            }
                        )

                item_count = (
                    db.query(QuestionnaireInvitationItem)
                    .filter(QuestionnaireInvitationItem.invitation_id == inv.id)
                    .count()
                )
                is_dynamic = bool(getattr(inv, "is_dynamic", False))
                if is_dynamic or item_count > 0:
                    q_status = None
                    completed_time = None

                    if inv.status == "completed":
                        q_status = QuestionnaireStatus.COMPLETED
                        if inv.completed_at:
                            completed_time = _as_utc(inv.completed_at).isoformat()
                    else:
                        if expires_utc and expires_utc < now_utc:
                            q_status = QuestionnaireStatus.UNANSWERED
                        else:
                            q_status = QuestionnaireStatus.PENDING

                    q_when = (
                        _as_utc(inv.completed_at)
                        if inv.status == "completed"
                        else when_sent
                    )
                    raw_events.append(
                        {
                            "id": f"quest_{inv.id}",
                            "date": _fmt_date(q_when),
                            "time": _fmt_time(q_when),
                            "title": "Cuestionario médico",
                            "actor": "Doctor",
                            "event_type": EventType.QUESTIONNAIRE,
                            "subtitle": (
                                "Cuestionario completado"
                                if q_status == QuestionnaireStatus.COMPLETED
                                else "Cuestionario de seguimiento"
                            ),
                            "description": (
                                "Se te envió un cuestionario médico para contestar."
                            ),
                            "raw_dt": q_when,
                            "questionnaire_status": q_status,
                            "completed_at": completed_time,
                        }
                    )
        except Exception as e:
            db.rollback()

            logger.error(f"Error en timeline (cuestionarios): {e}")

        raw_events.sort(key=lambda x: x["raw_dt"], reverse=True)

        pending_request_ids = set()
        try:
            pending_rows = (
                db.query(AnalysisRequest)
                .filter(
                    AnalysisRequest.patient_id == pid,
                    AnalysisRequest.status == "pending",
                    AnalysisRequest.document_id.is_(None),
                )
                .all()
            )
            pending_request_ids = {r.id for r in pending_rows}
        except Exception as e:
            db.rollback()
            logger.error(f"Error en timeline (pending rows): {e}")

        out: List[TimelineEventResponse] = []
        for e in raw_events:
            rid = e.get("analysis_request_id")
            forced = e.get("force_visual_state")
            if forced:
                vstate = forced
            elif e["raw_dt"] > now_utc:
                vstate = "future"
            elif rid and rid in pending_request_ids:
                vstate = "current"
            elif e.get("questionnaire_status") == QuestionnaireStatus.PENDING:
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
                    action_patient_id=e.get("action_patient_id"),
                    prior_documents_count=e.get("prior_documents_count"),
                )
            )

        return out

    @staticmethod
    def list_prior_documents_for_patient(
        db: Session, patient_id: str
    ) -> List[Document]:
        try:
            pid = UUID(str(patient_id))
        except (ValueError, TypeError):
            return []
        return _prior_documents_for_patient(db, pid)
