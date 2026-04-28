from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.models.folder import Folder


class FolderRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def _uid(self, user_id: str | uuid.UUID) -> uuid.UUID:
        if isinstance(user_id, uuid.UUID):
            return user_id
        return uuid.UUID(str(user_id))

    def get_by_user_and_drive_folder(
        self, user_id: str | uuid.UUID, drive_folder_id: str
    ) -> Optional[Folder]:
        uid = self._uid(user_id)
        return (
            self._db.query(Folder)
            .filter(Folder.user_id == uid, Folder.drive_folder_id == drive_folder_id)
            .first()
        )

    def create(
        self,
        user_id: str | uuid.UUID,
        *,
        name: str,
        category: str,
        drive_folder_id: str,
        drive_parent_id: str | None = None,
    ) -> Folder:
        uid = self._uid(user_id)
        row = Folder(
            user_id=uid,
            name=name,
            category=category,
            drive_folder_id=drive_folder_id,
            drive_parent_id=drive_parent_id,
        )
        self._db.add(row)
        self._db.commit()
        self._db.refresh(row)
        return row

    def get_or_create_for_category_drive(
        self, user_id: str, category: str, drive_folder_id: str
    ) -> Folder:
        existing = self.get_by_user_and_drive_folder(user_id, drive_folder_id)
        if existing:
            return existing
        return self.create(
            user_id,
            name=category,
            category=category,
            drive_folder_id=drive_folder_id,
            drive_parent_id=None,
        )
