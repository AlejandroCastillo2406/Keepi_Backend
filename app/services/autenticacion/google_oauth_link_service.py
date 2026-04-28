from __future__ import annotations

import base64
from datetime import datetime
from typing import List, Optional

from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.models.user_config import CloudProvider, UserConfigUpdate
from app.services.autenticacion import GoogleOAuthService
from app.services.autenticacion.oauth_credentials_service import OAuthCredentialsService
from app.services.usuarios.user_config_service import UserConfigService


class GoogleOAuthLinkService:
    def __init__(self, db: Session):
        self._db = db

    async def complete_mobile_callback(
        self,
        *,
        code: str,
        state: str,
        redirect_uri: str,
        app_deep_link_scheme: str,
    ) -> RedirectResponse:
        user_id = self._decode_state_user_id(state)
        if not user_id:
            return RedirectResponse(
                url=f"{app_deep_link_scheme}:/oauth2redirect?error=invalid_state"
            )
        try:
            oauth = GoogleOAuthService(self._db)
            await oauth.exchange_code_for_tokens(
                code, user_id, redirect_uri=redirect_uri
            )
            creds_svc = OAuthCredentialsService(self._db)
            saved = await creds_svc.get_user_credentials(user_id)
            if not saved:
                return RedirectResponse(
                    url=f"{app_deep_link_scheme}:/oauth2redirect?error=save_credentials_failed"
                )
            cfg = UserConfigService(self._db)
            await cfg.get_or_create_user_config(user_id)
            await cfg.update_user_config(
                user_id, UserConfigUpdate(cloud_provider=CloudProvider.GOOGLE_DRIVE)
            )
            return RedirectResponse(
                url=f"{app_deep_link_scheme}:/oauth2redirect?success=1"
            )
        except Exception:
            return RedirectResponse(
                url=f"{app_deep_link_scheme}:/oauth2redirect?error=1"
            )

    @staticmethod
    def _decode_state_user_id(state: str) -> str | None:
        if not state:
            return None
        try:
            padding = 4 - (len(state) % 4)
            state_padded = state + ("=" * padding if padding != 4 else "")
            return base64.b64decode(state_padded).decode("utf-8")
        except Exception:
            return None

    async def save_mobile_google_tokens(
        self,
        user_id: str,
        *,
        access_token: str,
        refresh_token: Optional[str] = None,
        scopes: Optional[List[str]] = None,
        expires_at: Optional[datetime] = None,
    ) -> None:
        oauth_cred = OAuthCredentialsService(self._db)
        ok = await oauth_cred.upsert_user_credentials(
            user_id,
            provider="google",
            access_token=access_token,
            refresh_token=refresh_token,
            scopes=scopes,
            expires_at=expires_at,
        )
        if not ok:
            raise RuntimeError("No se pudieron guardar credenciales OAuth")
        cfg = UserConfigService(self._db)
        await cfg.get_or_create_user_config(user_id)
        await cfg.update_user_config(
            user_id, UserConfigUpdate(cloud_provider=CloudProvider.GOOGLE_DRIVE)
        )
