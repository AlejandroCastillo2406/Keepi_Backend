from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.factories.notification_factory import get_notification_service
from app.services.documento.analysis_request_service import AnalysisRequestService
from app.services.medical.patient_timeline_service import PatientTimelineService
from app.services.medical.prescription_service import PrescriptionService
from app.services.medical.questionnaire_service import QuestionnaireService
from app.services.notificaciones.notification_service import NotificationService


def get_prescription_service(
    db: Session = Depends(get_db),
    notification_service: NotificationService = Depends(get_notification_service),
) -> PrescriptionService:
    return PrescriptionService(db, notification_service=notification_service)


def get_patient_timeline_service(
    db: Session = Depends(get_db),
) -> PatientTimelineService:
    return PatientTimelineService(db)


def get_analysis_request_service(
    db: Session = Depends(get_db),
    notification_service: NotificationService = Depends(get_notification_service),
) -> AnalysisRequestService:
    return AnalysisRequestService(db, notification_service=notification_service)


def get_questionnaire_service(db: Session = Depends(get_db)) -> QuestionnaireService:
    return QuestionnaireService(db)
