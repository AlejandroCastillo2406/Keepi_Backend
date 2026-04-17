from sqlalchemy.orm import Session
from sqlalchemy import and_
from uuid import UUID
from datetime import datetime
from typing import List, Optional
from app.models.analysis_request import AnalysisRequest

class AnalysisRequestRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, doctor_id: UUID, patient_id: UUID, description: str) -> AnalysisRequest:
        """Crea una nueva solicitud de análisis."""
        db_request = AnalysisRequest(
            doctor_id=doctor_id,
            patient_id=patient_id,
            description=description,
            status="pending"
        )
        self.db.add(db_request)
        self.db.commit()
        self.db.refresh(db_request)
        return db_request

    def get_by_id(self, request_id: UUID) -> Optional[AnalysisRequest]:
        """Busca una solicitud específica por su ID."""
        return self.db.query(AnalysisRequest).filter(AnalysisRequest.id == request_id).first()

    def get_pending_by_patient(self, patient_id: UUID) -> List[AnalysisRequest]:
        """Obtiene todas las solicitudes pendientes de un paciente específico."""
        return self.db.query(AnalysisRequest).filter(
            and_(
                AnalysisRequest.patient_id == patient_id,
                AnalysisRequest.status == "pending"
            )
        ).all()

    def get_all_by_patient(self, patient_id: UUID) -> List[AnalysisRequest]:
        """Obtiene el historial completo de solicitudes de un paciente (para el doctor)."""
        return self.db.query(AnalysisRequest).filter(
            AnalysisRequest.patient_id == patient_id
        ).order_by(AnalysisRequest.created_at.desc()).all()

    def mark_as_completed(self, request_id: UUID, document_id: UUID) -> Optional[AnalysisRequest]:
        """Vincula el documento subido y marca la solicitud como completada."""
        db_request = self.get_by_id(request_id)
        if db_request:
            db_request.document_id = document_id
            db_request.status = "completed"
            db_request.completed_at = datetime.utcnow()
            self.db.commit()
            self.db.refresh(db_request)
        return db_request