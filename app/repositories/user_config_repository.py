from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.models.user_config import UserConfig


class UserConfigRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def _uid(self, user_id: str | uuid.UUID) -> uuid.UUID:
        if isinstance(user_id, uuid.UUID):
            return user_id
        return uuid.UUID(str(user_id))

    def get_by_user_id(self, user_id: str | uuid.UUID) -> Optional[UserConfig]:
        uid = self._uid(user_id)
        return self._db.query(UserConfig).filter(UserConfig.user_id == uid).first()

    def add(self, row: UserConfig) -> UserConfig:
        self._db.add(row)
        self._db.commit()
        self._db.refresh(row)
        return row

    def save(self, row: UserConfig) -> UserConfig:
        self._db.commit()
        self._db.refresh(row)
        return row
