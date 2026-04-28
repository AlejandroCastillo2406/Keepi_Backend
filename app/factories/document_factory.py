from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.repositories.document_repository import DocumentRepository
from app.repositories.folder_repository import FolderRepository
from app.services.documento import DocumentService
from app.services.documento.document_api_service import DocumentApiService


def get_document_repository(db: Session = Depends(get_db)) -> DocumentRepository:
    return DocumentRepository(db)


def get_folder_repository(db: Session = Depends(get_db)) -> FolderRepository:
    return FolderRepository(db)


def get_document_service(
    repository: DocumentRepository = Depends(get_document_repository),
    folder_repository: FolderRepository = Depends(get_folder_repository),
    db: Session = Depends(get_db),
) -> DocumentService:
    return DocumentService(
        db=db,
        document_repository=repository,
        folder_repository=folder_repository,
    )


def get_document_api_service(
    db: Session = Depends(get_db),
    document_service: DocumentService = Depends(get_document_service),
) -> DocumentApiService:
    return DocumentApiService(db, document_service)
