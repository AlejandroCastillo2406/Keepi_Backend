"""
Repositorio de documentos: acceso a datos.
Todas las queries residen aquí; solo usa Models. Sin lógica de negocio.
"""
from typing import List, Optional

from sqlalchemy.orm import Session

from pydantic import BaseModel

from app.interfaces.repositories.document_repository import IDocumentRepository
from app.models.document import Document


class DocumentRepository(IDocumentRepository):
    """Implementación del repositorio de documentos. Solo queries con Model Document."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def get_by_user_id(self, user_id: str) -> List[Document]:
        return (
            self._db.query(Document)
            .filter(Document.user_id == user_id)
            .order_by(Document.created_at.desc())
            .all()
        )

    def get_by_id(self, document_id: str, user_id: str) -> Optional[Document]:
        return (
            self._db.query(Document)
            .filter(
                Document.id == document_id,
                Document.user_id == user_id,
            )
            .first()
        )

    def create(self, user_id: str, data: BaseModel) -> Document:
        payload = data.model_dump(exclude_unset=True)
        payload.setdefault("document_metadata", {})
        payload.setdefault("tags", [])
        payload.setdefault("ai_analysis", {})
        doc = Document(user_id=user_id, **payload)
        self._db.add(doc)
        self._db.commit()
        self._db.refresh(doc)
        return doc

    def update(
        self, document_id: str, user_id: str, data: BaseModel
    ) -> Optional[Document]:
        doc = self.get_by_id(document_id, user_id)
        if not doc:
            return None
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(doc, key, value)
        self._db.commit()
        self._db.refresh(doc)
        return doc

    def delete(self, document_id: str, user_id: str) -> bool:
        doc = self.get_by_id(document_id, user_id)
        if not doc:
            return False
        self._db.delete(doc)
        self._db.commit()
        return True
