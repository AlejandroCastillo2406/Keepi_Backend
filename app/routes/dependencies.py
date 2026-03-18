# Re-export: usar app.factories.dependencies como fuente de verdad
from app.core.database import get_db
from app.core.security import get_current_user
from app.factories.dependencies import (get_current_user_token,
                                        get_document_repository,
                                        get_document_service,
                                        get_subscription_service)

__all__ = [
    "get_db",
    "get_current_user",
    "get_current_user_token",
    "get_document_repository",
    "get_document_service",
    "get_subscription_service",
]
