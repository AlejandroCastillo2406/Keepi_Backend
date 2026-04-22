# Models Package
from .plans import Plan
from .medical_specialty import MedicalSpecialty
from .questionnaire_catalog import (
    DoctorQuestionnaireSettings,
    QuestionnaireAnswer,
    QuestionnaireQuestion,
    QuestionnaireQuestionOption,
    QuestionnaireResponse,
    QuestionnaireTemplate,
    QuestionnaireVersion,
)
from .appointment import Appointment, AppointmentProposal
from .document import Document
from .folder import Folder
from .notification import Notification
from .notifications_log import NotificationsLog
from .oauth_credentials import OAuthCredentials
from .patient_medical_record import PatientMedicalRecord
from .prescription import Prescription, PrescriptionItem
from .role import Role
from .subscription import Subscription
from .user import User
from .user_device_token import UserDeviceToken
from .user_config import UserConfig

# Exportar todos los modelos para que SQLAlchemy los registre
__all__ = [
    "User",
    "PatientMedicalRecord",
    "Prescription",
    "PrescriptionItem",
    "Role",
    "Document",
    "UserConfig",
    "Notification",
    "NotificationsLog",
    "Folder",
    "OAuthCredentials",
    "Subscription",
    "UserDeviceToken",
    "Plan",
    "Appointment",
    "AppointmentProposal",
    "MedicalSpecialty",
    "QuestionnaireTemplate",
    "QuestionnaireVersion",
    "QuestionnaireQuestion",
    "QuestionnaireQuestionOption",
    "DoctorQuestionnaireSettings",
    "QuestionnaireResponse",
    "QuestionnaireAnswer",
]