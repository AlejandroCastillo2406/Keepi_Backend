from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.models.oauth_credentials import OAuthCredentials


class OAuthCredentialsRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def _uid(self, user_id: str | uuid.UUID) -> uuid.UUID:
        if isinstance(user_id, uuid.UUID):
            return user_id
        return uuid.UUID(str(user_id))

    def get_by_user_provider(
        self, user_id: str | uuid.UUID, provider: str = "google"
    ) -> Optional[OAuthCredentials]:
        uid = self._uid(user_id)
        return (
            self._db.query(OAuthCredentials)
            .filter(
                OAuthCredentials.user_id == uid, OAuthCredentials.provider == provider
            )
            .first()
        )

    def to_dict(self, row: OAuthCredentials) -> Dict[str, Any]:
        return {
            "access_token": row.access_token,
            "refresh_token": row.refresh_token,
            "token_uri": row.token_uri,
            "client_id": row.client_id,
            "client_secret": row.client_secret,
            "scopes": row.scopes or [],
            "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        }

    def upsert_from_tokens(
        self,
        user_id: str | uuid.UUID,
        *,
        provider: str,
        access_token: str,
        refresh_token: Optional[str],
        token_uri: str,
        client_id: Optional[str],
        client_secret: Optional[str],
        scopes: Optional[list],
        expires_at: Optional[datetime],
    ) -> OAuthCredentials:
        uid = self._uid(user_id)
        existing = self.get_by_user_provider(uid, provider)
        if existing:
            existing.access_token = access_token
            existing.refresh_token = refresh_token
            existing.token_uri = token_uri
            existing.client_id = client_id
            existing.client_secret = client_secret
            existing.scopes = scopes or []
            existing.expires_at = expires_at
            existing.updated_at = datetime.now()
            self._db.commit()
            self._db.refresh(existing)
            return existing
        row = OAuthCredentials(
            user_id=uid,
            provider=provider,
            access_token=access_token,
            refresh_token=refresh_token,
            token_uri=token_uri,
            client_id=client_id,
            client_secret=client_secret,
            scopes=scopes or [],
            expires_at=expires_at,
        )
        self._db.add(row)
        self._db.commit()
        self._db.refresh(row)
        return row

    def upsert_from_google_credentials(
        self, user_id: str | uuid.UUID, credentials: Any, provider: str = "google"
    ) -> OAuthCredentials:
        uid = self._uid(user_id)
        existing = self.get_by_user_provider(uid, provider)
        if existing:
            existing.access_token = credentials.token
            existing.refresh_token = credentials.refresh_token
            existing.expires_at = credentials.expiry
            existing.updated_at = datetime.now()
            self._db.commit()
            self._db.refresh(existing)
            return existing
        row = OAuthCredentials(
            user_id=uid,
            provider=provider,
            access_token=credentials.token,
            refresh_token=credentials.refresh_token,
            token_uri=credentials.token_uri,
            client_id=credentials.client_id,
            client_secret=credentials.client_secret,
            scopes=credentials.scopes,
            expires_at=credentials.expiry,
        )
        self._db.add(row)
        self._db.commit()
        self._db.refresh(row)
        return row

    def update_tokens(
        self, user_id: str | uuid.UUID, credentials: Any, provider: str = "google"
    ) -> bool:
        row = self.get_by_user_provider(user_id, provider)
        if not row:
            return False
        row.access_token = credentials.token
        row.refresh_token = credentials.refresh_token
        row.expires_at = credentials.expiry
        row.updated_at = datetime.now()
        self._db.commit()
        return True

    def delete(self, user_id: str | uuid.UUID, provider: str = "google") -> bool:
        row = self.get_by_user_provider(user_id, provider)
        if not row:
            return False
        self._db.delete(row)
        self._db.commit()
        return True
