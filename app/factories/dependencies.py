"""
Inyección de dependencias: construcción de sesión BD y servicios con sus repositorios.
Una sola responsabilidad: exponer Depends(get_db), Depends(get_*_service) para las rutas.
"""
from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import verify_token
from app.repositories.document_repository import DocumentRepository
from app.services.documento import DocumentService
from app.services.subscription import SubscriptionService


def get_current_user_token(token: dict = Depends(verify_token)) -> dict:
    """Token JWT decodificado (uid, email, name, picture). Para rutas que no necesitan User ORM."""
    return token


def get_document_repository(db: Session = Depends(get_db)) -> DocumentRepository:
    return DocumentRepository(db)


def get_document_service(
    repository: DocumentRepository = Depends(get_document_repository),
    db: Session = Depends(get_db),
) -> DocumentService:
    return DocumentService(db=db, document_repository=repository)


def get_subscription_service() -> SubscriptionService:
    """SubscriptionService: sin estado; usa db por parámetro en cada método."""
    return SubscriptionService()
