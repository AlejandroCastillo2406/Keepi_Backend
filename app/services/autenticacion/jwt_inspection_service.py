from typing import Any, Dict, Optional

from fastapi.security import HTTPAuthorizationCredentials

from app.core.config import settings


class JwtInspectionService:
    @staticmethod
    def decode_bearer_optional(
        credentials: Optional[HTTPAuthorizationCredentials],
    ) -> Dict[str, Any]:
        if credentials is None:
            return {"error": "No se proporcionó token"}
        try:
            from jose import jwt

            token = credentials.credentials
            payload = jwt.decode(
                token,
                settings.jwt_secret_key,
                algorithms=[settings.jwt_algorithm],
                options={"verify_exp": False},
            )
            return {
                "token_payload": payload,
                "user_id_from_token": payload.get("sub"),
                "email_from_token": payload.get("email"),
            }
        except Exception as e:
            return {"error": f"Error decodificando token: {str(e)}"}
