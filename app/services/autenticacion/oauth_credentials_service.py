import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from google.oauth2.credentials import Credentials
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.repositories.oauth_credentials_repository import OAuthCredentialsRepository


def _google_oauth_defaults_from_secrets() -> tuple[str, Optional[str], Optional[str]]:
    path = Path(settings.google_client_secrets_path)
    if not path.is_absolute():
        backend_dir = Path(__file__).resolve().parent.parent.parent.parent
        path = backend_dir / path
    if not path.exists():
        return "https://oauth2.googleapis.com/token", None, None
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    web = data.get("web") or data.get("installed") or {}
    return (
        web.get("token_uri", "https://oauth2.googleapis.com/token"),
        web.get("client_id"),
        web.get("client_secret"),
    )


class OAuthCredentialsService:

    def __init__(
        self, db: Session, repository: OAuthCredentialsRepository | None = None
    ):
        self.db = db
        self._repo = repository or OAuthCredentialsRepository(db)

    def _to_uuid(self, user_id: str | uuid.UUID) -> uuid.UUID:
        if isinstance(user_id, uuid.UUID):
            return user_id
        return uuid.UUID(str(user_id))

    async def get_user_credentials(
        self, user_id: str, provider: str = "google"
    ) -> Optional[Dict[str, Any]]:
        try:
            row = self._repo.get_by_user_provider(user_id, provider)
            if row:
                return self._repo.to_dict(row)
            return None
        except Exception as e:
            print(f"Error obteniendo credenciales: {e}")
            return None

    async def save_user_credentials(
        self, user_id: str, credentials: Credentials, provider: str = "google"
    ) -> bool:
        try:
            self._repo.upsert_from_google_credentials(user_id, credentials, provider)
            return True
        except Exception as e:
            print(f"Error guardando credenciales: {e}")
            self.db.rollback()
            return False

    async def update_user_credentials(
        self, user_id: str, credentials: Credentials, provider: str = "google"
    ) -> bool:
        try:
            return self._repo.update_tokens(user_id, credentials, provider)
        except Exception as e:
            print(f"Error actualizando credenciales: {e}")
            self.db.rollback()
            return False

    async def delete_user_credentials(
        self, user_id: str, provider: str = "google"
    ) -> bool:
        try:
            return self._repo.delete(user_id, provider)
        except Exception as e:
            print(f"Error eliminando credenciales: {e}")
            self.db.rollback()
            return False

    async def upsert_user_credentials(
        self,
        user_id: str,
        *,
        provider: str = "google",
        access_token: str,
        refresh_token: Optional[str] = None,
        scopes: Optional[List[str]] = None,
        expires_at: Optional[datetime] = None,
    ) -> bool:
        try:
            token_uri, client_id, client_secret = _google_oauth_defaults_from_secrets()
            self._repo.upsert_from_tokens(
                user_id,
                provider=provider,
                access_token=access_token,
                refresh_token=refresh_token,
                token_uri=token_uri,
                client_id=client_id,
                client_secret=client_secret,
                scopes=scopes or [],
                expires_at=expires_at,
            )
            return True
        except Exception as e:
            print(f"Error en upsert_user_credentials: {e}")
            self.db.rollback()
            return False
