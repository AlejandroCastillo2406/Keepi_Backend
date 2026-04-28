from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.core.database import get_db
from app.auth.jwt_payloads import access_token_claims_for_user
from app.core.security import (
    create_access_token,
    create_refresh_token,
    get_current_user,
    require_no_temp_password_token,
    verify_refresh_token,
    verify_token,
)
from app.models.user import (
    PasswordChangeRequest,
    User,
    UserCreate,
    UserLogin,
    UserResponse,
)
from app.factories.user_factory import get_user_service
from app.services.autenticacion import GoogleOAuthService
from app.services.autenticacion.google_oauth_link_service import GoogleOAuthLinkService
from app.services.usuarios.user_service import UserService

router = APIRouter()


def _mobile_callback_base_url() -> str:
    uri = settings.google_redirect_uri or ""
    if "/api" in uri:
        return uri.rsplit("/api", 1)[0].rstrip("/")
    base = (settings.public_base_url or "").strip().rstrip("/")
    if not base:
        raise RuntimeError(
            "Configura PUBLIC_BASE_URL o GOOGLE_REDIRECT_URI para la URL base del callback móvil."
        )
    return base


MOBILE_CALLBACK_PATH = "/api/v1/auth/google/mobile-callback"
APP_DEEP_LINK_SCHEME = "com.example.keepi"

from pydantic import BaseModel


class GoogleMobileAuthRequest(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    id_token: Optional[str] = None
    expires_at: Optional[datetime] = None
    token_type: Optional[str] = None
    scopes: Optional[List[str]] = None


@router.post("/register")
async def register_user(
    user_data: UserCreate,
    user_service: UserService = Depends(get_user_service),
):
    try:
        if not user_data.password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Contraseña requerida para registro",
            )

        user = await user_service.create_user(user_data)

        access_token_expires = timedelta(minutes=30)
        access_token = create_access_token(
            data=access_token_claims_for_user(user),
            expires_delta=access_token_expires,
        )

        return {
            "access_token": access_token,
            "token_type": "bearer",
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
            "role_id": user.role_id,
            "role_name": user.role.name if user.role else "",
            "must_change_password": user.must_change_password,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error registrando usuario: {str(e)}",
        )


@router.post("/login")
async def login_user(
    login_data: UserLogin,
    user_service: UserService = Depends(get_user_service),
):
    try:
        result = await user_service.login_user(login_data)

        if not result:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Email o contraseña incorrectos",
            )

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error en login: {str(e)}",
        )


@router.post("/refresh")
async def refresh_token(
    refresh_token: str,
    user_service: UserService = Depends(get_user_service),
):
    try:
        payload = verify_refresh_token(refresh_token)
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token inválido o expirado",
            )

        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token inválido",
            )

        user = user_service.get_user_orm_by_uid(user_id)

        if not user or user.refresh_token != refresh_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token inválido",
            )

        access_token = create_access_token(data=access_token_claims_for_user(user))

        return {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": 30 * 60,
            "must_change_password": user.must_change_password,
            "role_id": user.role_id,
            "role_name": user.role.name if user.role else "",
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error renovando token: {str(e)}",
        )


@router.post("/change-password")
async def change_password(
    body: PasswordChangeRequest,
    current_user: User = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service),
):
    try:
        await user_service.change_password(
            str(current_user.id),
            body.current_password,
            body.new_password,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    user = user_service.get_user_orm_by_uid(str(current_user.id))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado"
        )

    claims = access_token_claims_for_user(user)
    access_token = create_access_token(
        data=claims,
        expires_delta=timedelta(minutes=30),
    )
    new_refresh = create_refresh_token(claims)
    user = user_service.set_refresh_token(str(current_user.id), new_refresh)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado"
        )

    return {
        "access_token": access_token,
        "refresh_token": new_refresh,
        "token_type": "bearer",
        "must_change_password": False,
        "user": UserResponse.from_orm(user),
    }


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service),
):
    u = await user_service.get_me_response(str(current_user.id))
    if not u:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return u


@router.get("/verify")
async def verify_authentication(
    user_token: dict = Depends(verify_token),
    user_service: UserService = Depends(get_user_service),
):
    try:
        return user_service.verify_registered_user_from_token(user_token)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.get("/current-user")
async def current_user_from_token(
    user_token: dict = Depends(verify_token),
    user_service: UserService = Depends(get_user_service),
):
    try:
        user = await user_service.get_user_by_uid(user_token["uid"])

        if user:
            return user
        else:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/google/authorize")
async def authorize_google_drive(
    user_token: dict = Depends(require_no_temp_password_token),
    db: Session = Depends(get_db),
):
    try:
        oauth_service = GoogleOAuthService(db)

        import base64

        user_id = user_token["uid"]
        state = base64.b64encode(user_id.encode("utf-8")).decode("utf-8")

        print(f"🔐 Generando autorización para usuario: {user_id}")
        print(f"🔐 State generado: {state}")

        auth_data = await oauth_service.get_authorization_url(user_id)

        return {
            "message": "URL de autorización generada",
            "authorization_url": auth_data["authorization_url"],
            "state": state,
            "user_id": user_id,
        }

    except Exception as e:
        print(f"❌ Error en autorización Google Drive: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/google/mobile-authorize")
async def mobile_authorize_google_drive(
    user_token: dict = Depends(require_no_temp_password_token),
    db: Session = Depends(get_db),
):
    try:
        user_id = user_token["uid"]
        base_url = _mobile_callback_base_url()
        redirect_uri = f"{base_url}{MOBILE_CALLBACK_PATH}"
        oauth_service = GoogleOAuthService(db)
        auth_data = await oauth_service.get_authorization_url(
            user_id, redirect_uri=redirect_uri
        )
        return {
            "authorization_url": auth_data["authorization_url"],
            "state": auth_data["state"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/google/mobile-callback")
async def google_mobile_callback(
    code: str = Query(..., description="Código de autorización"),
    state: str = Query(..., description="State con user_id"),
    db: Session = Depends(get_db),
):
    base_url = _mobile_callback_base_url()
    redirect_uri = f"{base_url}{MOBILE_CALLBACK_PATH}"
    link_svc = GoogleOAuthLinkService(db)
    return await link_svc.complete_mobile_callback(
        code=code,
        state=state,
        redirect_uri=redirect_uri,
        app_deep_link_scheme=APP_DEEP_LINK_SCHEME,
    )


@router.get("/google/status")
async def check_google_drive_status(
    user_token: dict = Depends(require_no_temp_password_token),
    db: Session = Depends(get_db),
):
    try:
        oauth_service = GoogleOAuthService(db)
        status = await oauth_service.check_user_drive_access(user_token["uid"])

        return status

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/google/revoke")
async def revoke_google_drive_access(
    user_token: dict = Depends(require_no_temp_password_token),
    db: Session = Depends(get_db),
):
    try:
        oauth_service = GoogleOAuthService(db)
        success = await oauth_service.revoke_user_access(user_token["uid"])

        if success:
            return {
                "message": "Acceso a Google Drive revocado exitosamente",
                "access_revoked": True,
            }
        else:
            raise HTTPException(status_code=500, detail="Error revocando acceso")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/google/refresh")
async def refresh_google_drive_tokens(
    user_token: dict = Depends(require_no_temp_password_token),
    db: Session = Depends(get_db),
):
    try:
        oauth_service = GoogleOAuthService(db)
        credentials = await oauth_service.refresh_user_tokens(user_token["uid"])

        if credentials:
            return {
                "message": "Tokens renovados exitosamente",
                "access_token": credentials.token,
                "expires_at": (
                    credentials.expiry.isoformat() if credentials.expiry else None
                ),
                "refreshed": True,
            }
        else:
            raise HTTPException(
                status_code=400, detail="No se pudieron renovar los tokens"
            )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/google/mobile-auth")
async def google_mobile_auth(
    payload: GoogleMobileAuthRequest,
    user_token: dict = Depends(require_no_temp_password_token),
    db: Session = Depends(get_db),
):
    try:
        link_svc = GoogleOAuthLinkService(db)
        await link_svc.save_mobile_google_tokens(
            user_token["uid"],
            access_token=payload.access_token,
            refresh_token=payload.refresh_token,
            scopes=payload.scopes,
            expires_at=payload.expires_at,
        )
        return {"success": True, "message": "Google Drive vinculado correctamente"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error procesando autenticación móvil de Google: {str(e)}",
        )
