from __future__ import annotations

import uuid
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.user_device_token import UserDeviceToken


class UserDeviceTokenRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_by_token_value(self, token: str) -> Optional[UserDeviceToken]:
        return (
            self._db.query(UserDeviceToken)
            .filter(UserDeviceToken.token == token)
            .first()
        )

    def save(self, row: UserDeviceToken) -> UserDeviceToken:
        self._db.commit()
        self._db.refresh(row)
        return row

    def list_active_for_user(self, user_id: uuid.UUID) -> List[UserDeviceToken]:
        return (
            self._db.query(UserDeviceToken)
            .filter(
                UserDeviceToken.user_id == user_id, UserDeviceToken.is_active.is_(True)
            )
            .all()
        )

    def deactivate_by_id(self, token_id: uuid.UUID) -> None:
        row = (
            self._db.query(UserDeviceToken)
            .filter(UserDeviceToken.id == token_id)
            .first()
        )
        if row is not None:
            row.is_active = False
            self._db.commit()

    def deactivate_other_tokens_for_user(
        self, user_id: uuid.UUID, *, keep_token: str
    ) -> int:
        """Desactiva tokens viejos del mismo usuario (otro dispositivo / sesión FCM expirada)."""
        q = self._db.query(UserDeviceToken).filter(
            UserDeviceToken.user_id == user_id,
            UserDeviceToken.token != keep_token,
            UserDeviceToken.is_active.is_(True),
        )
        count = q.update({UserDeviceToken.is_active: False}, synchronize_session=False)
        if count:
            self._db.commit()
        return count
