# Models Package
from .user import User
from .document import Document
from .ai_analysis import AIAnalysis
from .user_config import UserConfig
from .notification import Notification
from .folder import Folder
from .oauth_credentials import OAuthCredentials
from .subscription import Subscription

# Exportar todos los modelos para que SQLAlchemy los registre
__all__ = [
    "User",
    "Document", 
    "AIAnalysis",
    "UserConfig",
    "Notification",
    "Folder",
    "OAuthCredentials",
    "Subscription"
]