# Models Package
from .document import Document
from .folder import Folder
from .notification import Notification
from .oauth_credentials import OAuthCredentials
from .subscription import Subscription
from .user import User
from .user_config import UserConfig

# Exportar todos los modelos para que SQLAlchemy los registre
__all__ = [
    "User",
    "Document",
    "UserConfig",
    "Notification",
    "Folder",
    "OAuthCredentials",
    "Subscription",
]