# Models Package
from .plans import Plan
from .document import Document
from .folder import Folder
from .notification import Notification
from .notifications_log import NotificationsLog
from .oauth_credentials import OAuthCredentials
from .patient_medical_record import PatientMedicalRecord
from .role import Role
from .subscription import Subscription
from .user import User
from .user_config import UserConfig

# Exportar todos los modelos para que SQLAlchemy los registre
__all__ = [
    "User",
    "PatientMedicalRecord",
    "Role",
    "Document",
    "UserConfig",
    "Notification",
    "NotificationsLog",
    "Folder",
    "OAuthCredentials",
    "Subscription",
    "Plan",
]