from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List, Optional, Literal
from datetime import datetime
from pydantic import BaseModel
import uuid

from app.core.database import get_db
from app.models.appointment import Appointment
from app.models.document import Document
from app.models.analysis_request import AnalysisRequest
from app.models.user import User


from app.core.security import get_current_user 

router = APIRouter(tags=["Global Search"])

class GlobalSearchItem(BaseModel):
    id: str
    type: Literal["appointment", "document", "analysis"]
    title: str
    subtitle: Optional[str] = None
    patient_id: Optional[str] = None
    date: datetime
    status: Optional[str] = None

class GlobalSearchResponse(BaseModel):
    results: List[GlobalSearchItem]
    total: int

@router.get("/", response_model=GlobalSearchResponse)
def global_search(
    patient_id: Optional[uuid.UUID] = Query(None, description="CP-21: Buscar por paciente"),
    item_type: Optional[str] = Query(None, description="CP-22: Buscar por tipo"),
    status: Optional[str] = Query(None, description="CP-23: Buscar por estado"),
    start_date: Optional[datetime] = Query(None, description="CP-24: Rango de fechas - Inicio"),
    end_date: Optional[datetime] = Query(None, description="CP-24: Rango de fechas - Fin"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user) # 🔐 TOKEN BEARER REQUERIDO AQUÍ
):
    results: List[GlobalSearchItem] = []
    
   
    user_id = current_user.id

    
    if not item_type or item_type.lower() == "appointment":
        query = db.query(Appointment).filter(
            or_(Appointment.doctor_id == user_id, Appointment.patient_id == user_id)
        )
        if patient_id:
            query = query.filter(Appointment.patient_id == patient_id)
        if status:
            query = query.filter(Appointment.status == status)
        if start_date:
            query = query.filter(Appointment.appointment_date >= start_date)
        if end_date:
            query = query.filter(Appointment.appointment_date <= end_date)
        
        for appt in query.all():
            results.append(GlobalSearchItem(
                id=str(appt.id),
                type="appointment",
                title=appt.reason if appt.reason else "Cita médica",
                subtitle=f"Estado: {appt.status}",
                patient_id=str(appt.patient_id),
                date=appt.appointment_date or appt.created_at,
                status=appt.status
            ))

    
    if not item_type or item_type.lower() == "document":
        query = db.query(Document).filter(Document.user_id == user_id)
        if status:
            pass 
        if start_date:
            query = query.filter(Document.created_at >= start_date)
        if end_date:
            query = query.filter(Document.created_at <= end_date)
            
        for doc in query.all():
            results.append(GlobalSearchItem(
                id=str(doc.id),
                type="document",
                title=doc.name,
                subtitle=doc.category,
                patient_id=str(doc.user_id), 
                date=doc.created_at,
                status=doc.category
            ))

   
    if not item_type or item_type.lower() == "analysis":
        query = db.query(AnalysisRequest).filter(
            or_(AnalysisRequest.doctor_id == user_id, AnalysisRequest.patient_id == user_id)
        )
        if patient_id:
            query = query.filter(AnalysisRequest.patient_id == patient_id)
        if status:
            query = query.filter(AnalysisRequest.status == status)
        if start_date:
            query = query.filter(AnalysisRequest.created_at >= start_date)
        if end_date:
            query = query.filter(AnalysisRequest.created_at <= end_date)
            
        for analysis in query.all():
            results.append(GlobalSearchItem(
                id=str(analysis.id),
                type="analysis",
                title=analysis.description if analysis.description else "Solicitud de Análisis",
                subtitle=f"Estado: {analysis.status}",
                patient_id=str(analysis.patient_id) if analysis.patient_id else None,
                date=analysis.created_at,
                status=analysis.status
            ))

    # Ordenar del más reciente al más antiguo
    results.sort(key=lambda x: x.date, reverse=True)

    return {"results": results, "total": len(results)}