from __future__ import annotations

from datetime import date
from typing import Any, List, NamedTuple

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.user import User


def _not_replaced_filter():
    """Excluye documentos ya marcados como reemplazados en ai_analysis."""
    replaced = Document.ai_analysis.op("->>")("replaced")
    return or_(
        Document.ai_analysis.is_(None),
        replaced.is_(None),
        replaced != "true",
    )


class ExpiryCandidateRow(NamedTuple):
    document_id: Any
    document_file_name: Any
    document_name: Any
    user_id: Any
    email: Any
    user_name: Any


class ExpiryCandidateRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def list_candidates_for_expiry_date(
        self, expiry_date: date
    ) -> List[ExpiryCandidateRow]:
        rows = (
            self._db.query(
                Document.id.label("document_id"),
                Document.file_name.label("document_file_name"),
                Document.name.label("document_name"),
                User.id.label("user_id"),
                User.email.label("email"),
                User.name.label("user_name"),
            )
            .join(User, User.id == Document.user_id)
            .filter(Document.is_archived.is_(False))
            .filter(Document.expiry_date.isnot(None))
            .filter(_not_replaced_filter())
            .filter(User.is_active.is_(True))
            .filter(
                func.date(func.timezone("UTC", Document.expiry_date)) == expiry_date
            )
            .all()
        )
        return [
            ExpiryCandidateRow(
                document_id=r.document_id,
                document_file_name=r.document_file_name,
                document_name=r.document_name,
                user_id=r.user_id,
                email=r.email,
                user_name=r.user_name,
            )
            for r in rows
        ]
