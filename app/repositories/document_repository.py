import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.interfaces.document_interface import IDocumentRepository
from app.models.document import Document


class DocumentRepository(IDocumentRepository):

    def __init__(self, db: Session) -> None:
        self._db = db

    def _user_uuid(self, user_id: str) -> uuid.UUID:
        return uuid.UUID(str(user_id))

    def get_by_user_id(self, user_id: str) -> List[Document]:
        uid = self._user_uuid(user_id)
        return (
            self._db.query(Document)
            .filter(Document.user_id == uid)
            .order_by(Document.created_at.desc())
            .all()
        )

    def get_by_id(self, document_id: str, user_id: str) -> Optional[Document]:
        uid = self._user_uuid(user_id)
        try:
            did = uuid.UUID(str(document_id))
        except (ValueError, TypeError):
            return None
        return (
            self._db.query(Document)
            .filter(Document.id == did, Document.user_id == uid)
            .first()
        )

    def create(self, user_id: str, data: BaseModel) -> Document:
        payload = data.model_dump(exclude_unset=True)
        payload.pop("drive_folder_id", None)
        payload.setdefault("document_metadata", {})
        payload.setdefault("tags", [])
        payload.setdefault("ai_analysis", {})
        doc = Document(user_id=self._user_uuid(user_id), **payload)
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

    def get_by_id_any_user(self, document_id) -> Document | None:
        return self._db.query(Document).filter(Document.id == document_id).first()

    def persist(self, doc: Document) -> Document:
        self._db.add(doc)
        self._db.commit()
        self._db.refresh(doc)
        return doc

    def list_for_user_drive_file_ids(
        self, user_id: uuid.UUID, drive_file_ids: List[str]
    ) -> List[Document]:
        if not drive_file_ids:
            return []
        return (
            self._db.query(Document)
            .filter(
                Document.user_id == user_id,
                Document.drive_file_id.in_(drive_file_ids),
            )
            .all()
        )

    def list_distinct_categories(self, user_id: str) -> List[str]:
        uid = self._user_uuid(user_id)
        rows = (
            self._db.query(Document.category)
            .filter(Document.user_id == uid)
            .distinct()
            .all()
        )
        return [r[0] for r in rows if r[0] is not None]

    def list_expiring_before(self, user_id: str, cutoff: datetime) -> List[Document]:
        uid = self._user_uuid(user_id)
        return (
            self._db.query(Document)
            .filter(
                Document.user_id == uid,
                Document.expiry_date.isnot(None),
                Document.expiry_date <= cutoff,
            )
            .all()
        )

    def search_by_user_text(self, user_id: str, query: str) -> List[Document]:
        uid = self._user_uuid(user_id)
        q = f"%{query.lower()}%"
        return (
            self._db.query(Document)
            .filter(
                Document.user_id == uid,
                or_(
                    Document.name.ilike(q),
                    Document.description.ilike(q),
                    Document.category.ilike(q),
                ),
            )
            .all()
        )
