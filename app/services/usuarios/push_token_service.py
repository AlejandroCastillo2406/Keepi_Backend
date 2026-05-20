from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models.user_device_token import (
    RegisterDeviceTokenRequest,
    RegisterDeviceTokenResponse,
    UserDeviceToken,
)
from app.repositories.user_device_token_repository import UserDeviceTokenRepository


class PushTokenService:
    def __init__(
        self,
        db: Session,
        token_repository: UserDeviceTokenRepository | None = None,
    ) -> None:
        self._db = db
        self._tokens = token_repository or UserDeviceTokenRepository(db)

    def register_token(
        self, user_id: uuid.UUID, body: RegisterDeviceTokenRequest
    ) -> RegisterDeviceTokenResponse:
        row = self._tokens.get_by_token_value(body.token)
        if row is None:
            row = UserDeviceToken(
                user_id=user_id,
                token=body.token,
                platform=body.platform,
                is_active=True,
            )
            self._db.add(row)
        else:
            row.user_id = user_id
            row.platform = body.platform
            row.is_active = True
        self._tokens.deactivate_other_tokens_for_user(
            user_id, keep_token=body.token
        )
        self._tokens.save(row)
        return RegisterDeviceTokenResponse(
            token=row.token,
            platform=row.platform,
            updated_at=row.updated_at,
        )
