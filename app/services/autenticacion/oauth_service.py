import base64
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.services.autenticacion.oauth_credentials_service import OAuthCredentialsService

logger = logging.getLogger(__name__)


class GoogleOAuthService:

    def __init__(self, db: Session):
        self._db = db

        self.client_secrets_file = settings.google_client_secrets_path
        self.scopes = [
            "openid",
            "https://www.googleapis.com/auth/drive.file",
            "https://www.googleapis.com/auth/drive.metadata.readonly",
            "https://www.googleapis.com/auth/userinfo.email",
        ]

        self.redirect_uri = (
            settings.google_redirect_uri
            or f"{settings.host}/api/v1/auth/google/callback"
        )

    async def get_authorization_url(
        self, user_id: str, redirect_uri: Optional[str] = None
    ) -> Dict[str, str]:
        try:
            uri = redirect_uri or self.redirect_uri
            flow = Flow.from_client_secrets_file(
                self.client_secrets_file, scopes=self.scopes, redirect_uri=uri
            )

            state = base64.b64encode(user_id.encode("utf-8")).decode("utf-8")

            flow.state = state

            authorization_url, _ = flow.authorization_url(
                access_type="offline",
                include_granted_scopes="true",
                prompt="consent",
                state=state,
                login_hint=None,
            )

            logger.info("OAuth: URL de autorización generada para user_id=%s", user_id)
            return {"authorization_url": authorization_url, "state": state}

        except Exception:
            logger.exception("OAuth: Error generando URL de autorización")
            raise

    async def exchange_code_for_tokens(
        self,
        authorization_code: str,
        user_id: str,
        redirect_uri: Optional[str] = None,
    ) -> Dict[str, Any]:
        try:
            uri = redirect_uri or self.redirect_uri
            flow = Flow.from_client_secrets_file(
                self.client_secrets_file, scopes=self.scopes, redirect_uri=uri
            )

            flow.fetch_token(code=authorization_code)

            credentials = flow.credentials

            if not user_id:
                user_id = "default_user"
                logger.warning("OAuth: user_id vacío, usando valor por defecto")
            logger.info("OAuth: Guardando credenciales para user_id=%s", user_id)

            await self._save_user_credentials(user_id, credentials)

            return {
                "access_token": credentials.token,
                "refresh_token": credentials.refresh_token,
                "expires_at": (
                    credentials.expiry.isoformat() if credentials.expiry else None
                ),
                "scopes": credentials.scopes,
                "user_id": user_id,
            }

        except Exception:
            logger.exception("OAuth: Error intercambiando código por tokens")
            raise

    async def refresh_user_tokens(self, user_id: str) -> Optional[Credentials]:
        try:

            credentials_data = await self._get_user_credentials(user_id)

            if not credentials_data:
                return None

            credentials = Credentials(
                token=credentials_data.get("access_token"),
                refresh_token=credentials_data.get("refresh_token"),
                token_uri="https://oauth2.googleapis.com/token",
                client_id=credentials_data.get("client_id"),
                client_secret=credentials_data.get("client_secret"),
                scopes=credentials_data.get("scopes", self.scopes),
            )

            if credentials.refresh_token:
                try:
                    credentials.refresh(Request())
                    logger.info(
                        "OAuth: Token Google refrescado para user_id=%s", user_id
                    )
                    await self._update_user_credentials(user_id, credentials)
                    logger.info(
                        "OAuth: Credenciales actualizadas para user_id=%s", user_id
                    )
                except Exception as refresh_error:
                    logger.warning(
                        "OAuth: Error refrescando token Google para user_id=%s: %s",
                        user_id,
                        refresh_error,
                    )
                    return None
            else:
                logger.warning("OAuth: Sin refresh_token para user_id=%s", user_id)
                return None

            return credentials

        except Exception:
            logger.exception("OAuth: Error refrescando tokens")
            return None

    async def revoke_user_access(self, user_id: str) -> bool:
        try:

            await self._delete_user_credentials(user_id)
            return True

        except Exception:
            logger.exception("OAuth: Error revocando acceso para user_id=%s", user_id)
            return False

    async def check_user_drive_access(self, user_id: str) -> Dict[str, Any]:
        try:
            credentials_data = await self._get_user_credentials(user_id)

            if not credentials_data:
                return {
                    "has_access": False,
                    "status": "no_credentials",
                    "message": "Usuario no ha autorizado acceso a Google Drive",
                    "requires_action": "authorize",
                }

            expires_at = credentials_data.get("expires_at")
            current_time = datetime.now()

            if expires_at:
                try:
                    expiry_time = datetime.fromisoformat(expires_at)

                    if expiry_time.tzinfo is not None:
                        expiry_time = expiry_time.replace(tzinfo=None)
                    if current_time.tzinfo is not None:
                        current_time = current_time.replace(tzinfo=None)

                    time_until_expiry = expiry_time - current_time
                except Exception as e:
                    logger.warning("OAuth: Error procesando fecha de expiración: %s", e)

                    return {
                        "has_access": False,
                        "status": "error",
                        "message": f"Error verificando acceso: {str(e)}",
                        "requires_action": "authorize",
                    }

                if time_until_expiry.total_seconds() < 300:
                    return {
                        "has_access": False,
                        "status": "expired",
                        "message": "Token expirado o próximo a expirar, requiere renovación",
                        "expires_at": expires_at,
                        "time_until_expiry": time_until_expiry.total_seconds(),
                        "requires_action": "refresh",
                    }

            try:
                credentials = Credentials(
                    token=credentials_data.get("access_token"),
                    refresh_token=credentials_data.get("refresh_token"),
                    token_uri="https://oauth2.googleapis.com/token",
                    client_id=credentials_data.get("client_id"),
                    client_secret=credentials_data.get("client_secret"),
                    scopes=credentials_data.get("scopes", self.scopes),
                )

                if credentials.expired and credentials.refresh_token:
                    credentials.refresh(Request())
                    await self._update_user_credentials(user_id, credentials)

                return {
                    "has_access": True,
                    "status": "active",
                    "message": "Usuario tiene acceso activo a Google Drive",
                    "scopes": credentials_data.get("scopes", []),
                    "expires_at": (
                        credentials.expiry.isoformat()
                        if credentials.expiry
                        else expires_at
                    ),
                    "requires_action": "none",
                }

            except Exception as refresh_error:
                logger.warning(
                    "OAuth: Error refrescando token al verificar acceso: %s",
                    refresh_error,
                )
                return {
                    "has_access": False,
                    "status": "invalid_credentials",
                    "message": "Credenciales inválidas, requiere reautorización",
                    "requires_action": "authorize",
                }

        except Exception as e:
            logger.exception("OAuth: Error verificando acceso Drive")
            return {
                "has_access": False,
                "status": "error",
                "message": f"Error verificando acceso: {str(e)}",
                "requires_action": "authorize",
            }

    async def get_user_id_from_temp_code(self, code: str) -> Optional[str]:
        try:

            flow = Flow.from_client_secrets_file(
                self.client_secrets_file,
                scopes=self.scopes,
                redirect_uri=self.redirect_uri,
            )

            flow.fetch_token(code=code)
            credentials = flow.credentials

            logger.debug("OAuth: Código recibido, scopes=%s", credentials.scopes)
            return None
        except Exception as e:
            logger.warning("OAuth: No se pudo obtener user_id del código: %s", e)
            return None

    async def _save_user_credentials(
        self, user_id: str, credentials: Credentials
    ) -> bool:
        try:
            oauth_service = OAuthCredentialsService(self._db)
            success = await oauth_service.save_user_credentials(user_id, credentials)

            if success:
                logger.info("OAuth: Credenciales guardadas para user_id=%s", user_id)
            return success
        except Exception:
            logger.exception("OAuth: Error guardando credenciales")
            return False

    async def _get_user_credentials(self, user_id: str) -> Optional[Dict[str, Any]]:
        try:
            oauth_service = OAuthCredentialsService(self._db)
            return await oauth_service.get_user_credentials(user_id)

        except Exception:
            logger.exception("OAuth: Error obteniendo credenciales")
            return None

    async def _update_user_credentials(
        self, user_id: str, credentials: Credentials
    ) -> bool:
        try:
            oauth_service = OAuthCredentialsService(self._db)
            return await oauth_service.update_user_credentials(user_id, credentials)

        except Exception:
            logger.exception("OAuth: Error actualizando credenciales")
            return False

    async def _delete_user_credentials(self, user_id: str) -> bool:
        try:
            oauth_service = OAuthCredentialsService(self._db)
            return await oauth_service.delete_user_credentials(user_id)

        except Exception:
            logger.exception("OAuth: Error eliminando credenciales")
            return False
