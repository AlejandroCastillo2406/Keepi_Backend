# Models Package
from .user import User
from .document import Document
from .ai_analysis import AIAnalysis, AIAnalysisHistory
from .user_config import UserConfig
from .notification import Notification
from .folder import Folder
from .audit_log import AuditLog
from .backup_sync import BackupSync, SyncConflict
from .search_index import SearchIndex
from .oauth_credentials import OAuthCredentials

# Exportar todos los modelos para que SQLAlchemy los registre
__all__ = [
    "User",
    "Document", 
    "AIAnalysis",
    "AIAnalysisHistory",
    "UserConfig",
    "Notification",
    "Folder",
    "AuditLog",
    "BackupSync",
    "SyncConflict",
    "SearchIndex",
    "OAuthCredentials"
]