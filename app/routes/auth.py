from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.core.database import get_db
from app.auth.jwt_payloads import access_token_claims_for_user
from app.core.security import (create_access_token, create_refresh_token,
                               get_current_user, require_no_temp_password_token,
                               verify_refresh_token, verify_token)
from app.models.user import (PasswordChangeRequest, User, UserCreate, UserLogin,
                             UserResponse)
from app.services.autenticacion import GoogleOAuthService
from app.services.health_questionnaire_service import (
    build_user_response_with_flags,
    patient_must_complete_questionnaire,
    seed_catalog_if_empty,
)
from app.services.usuarios import UserService

router = APIRouter()

# Base URL pública del backend (para callback móvil HTTPS)
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
async def register_user(user_data: UserCreate, db: Session = Depends(get_db)):
    """Registrar nuevo usuario y devolver token de acceso"""
    try:
        if not user_data.password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Contraseña requerida para registro"
            )
        
        user_service = UserService(db)
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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error registrando usuario: {str(e)}"
        )

@router.post("/login")
async def login_user(login_data: UserLogin, db: Session = Depends(get_db)):
    """Iniciar sesión de usuario"""
    try:
        user_service = UserService(db)
        result = await user_service.login_user(login_data)
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Email o contraseña incorrectos"
            )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error en login: {str(e)}"
        )

@router.post("/refresh")
async def refresh_token(refresh_token: str, db: Session = Depends(get_db)):
    """Renovar token de acceso usando refresh token """
    try:
        payload = verify_refresh_token(refresh_token)
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token inválido o expirado"
            )

        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token inválido"
            )

        user_service = UserService(db)
        user = user_service.get_user_orm_by_uid(user_id)

        if not user or user.refresh_token != refresh_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token inválido"
            )

        access_token = create_access_token(data=access_token_claims_for_user(user))
        seed_catalog_if_empty(db)
        pending_q = patient_must_complete_questionnaire(db, user)

        return {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": 30 * 60,
            "must_change_password": user.must_change_password,
            "role_id": user.role_id,
            "role_name": user.role.name if user.role else "",
            "pending_health_questionnaire": pending_q,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error renovando token: {str(e)}"
        )


@router.post("/change-password")
async def change_password(
    body: PasswordChangeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Cambio de contraseña (incluye obligatorio para pacientes con contraseña temporal)."""
    user_service = UserService(db)
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")

    claims = access_token_claims_for_user(user)
    access_token = create_access_token(
        data=claims,
        expires_delta=timedelta(minutes=30),
    )
    new_refresh = create_refresh_token(claims)
    user.refresh_token = new_refresh
    db.commit()

    seed_catalog_if_empty(db)
    uresp = build_user_response_with_flags(db, user)
    return {
        "access_token": access_token,
        "refresh_token": new_refresh,
        "token_type": "bearer",
        "must_change_password": False,
        "pending_health_questionnaire": uresp.pending_health_questionnaire,
        "user": uresp,
    }


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Obtener información del usuario actual"""
    return build_user_response_with_flags(db, current_user)

@router.get("/verify")
async def verify_authentication(user_token: dict = Depends(verify_token)):
    """Verificar token de autenticación"""
    return {
        "authenticated": True,
        "user_id": user_token['uid'],
        "email": user_token['email']
    }

@router.get("/current-user")
async def current_user_from_token(user_token: dict = Depends(verify_token), db: Session = Depends(get_db)):
    """Obtener información del usuario actual"""
    try:
        user_service = UserService(db)
        user = await user_service.get_user_by_uid(user_token['uid'])
        
        if user:
            return user
        else:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/google/authorize")
async def authorize_google_drive(user_token: dict = Depends(require_no_temp_password_token)):
    """Generar URL de autorización para Google Drive"""
    try:
        oauth_service = GoogleOAuthService()
        
        # Generar un state que contenga el user_id del usuario logueado
        import base64
        user_id = user_token['uid']
        state = base64.b64encode(user_id.encode('utf-8')).decode('utf-8')
        
        print(f"🔐 Generando autorización para usuario: {user_id}")
        print(f"🔐 State generado: {state}")
        
        auth_data = await oauth_service.get_authorization_url(user_id)
        
        return {
            "message": "URL de autorización generada",
            "authorization_url": auth_data["authorization_url"],
            "state": state,
            "user_id": user_id
        }
        
    except Exception as e:
        print(f"❌ Error en autorización Google Drive: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/google/mobile-authorize")
async def mobile_authorize_google_drive(
    user_token: dict = Depends(require_no_temp_password_token),
    db: Session = Depends(get_db),
):
    """
    URL de autorización para la app móvil.
    Usa redirect_uri HTTPS (mobile-callback) para cumplir con Google; luego el backend redirige a la app.
    """
    try:
        user_id = user_token["uid"]
        base_url = _mobile_callback_base_url()
        redirect_uri = f"{base_url}{MOBILE_CALLBACK_PATH}"
        oauth_service = GoogleOAuthService(db)
        auth_data = await oauth_service.get_authorization_url(user_id, redirect_uri=redirect_uri)
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
    """
    Callback HTTPS para OAuth móvil. Intercambia code por tokens, guarda en BD,
    marca cloud_provider=google_drive y redirige a la app (deep link).
    """
    try:
        import base64
        user_id = None
        if state:
            try:
                padding = 4 - (len(state) % 4)
                if padding != 4:
                    state_padded = state + "=" * padding
                else:
                    state_padded = state
                user_id = base64.b64decode(state_padded).decode("utf-8")
            except Exception:
                pass
        if not user_id:
            return RedirectResponse(
                url=f"{APP_DEEP_LINK_SCHEME}:/oauth2redirect?error=invalid_state"
            )
        base_url = _mobile_callback_base_url()
        redirect_uri = f"{base_url}{MOBILE_CALLBACK_PATH}"
        oauth_service = GoogleOAuthService(db)
        await oauth_service.exchange_code_for_tokens(
            code, user_id, redirect_uri=redirect_uri
        )
        from app.services.autenticacion import OAuthCredentialsService
        saved_creds = await OAuthCredentialsService(db).get_user_credentials(user_id)
        if not saved_creds:
            print(f"OAuth: no se guardaron credenciales para user_id={user_id}")
            return RedirectResponse(
                url=f"{APP_DEEP_LINK_SCHEME}:/oauth2redirect?error=save_credentials_failed"
            )
        from app.models.user_config import CloudProvider, UserConfigUpdate
        from app.services.usuarios import UserConfigService
        config_service = UserConfigService(db)
        await config_service.get_or_create_user_config(user_id)
        await config_service.update_user_config(
            user_id, UserConfigUpdate(cloud_provider=CloudProvider.GOOGLE_DRIVE)
        )
        return RedirectResponse(
            url=f"{APP_DEEP_LINK_SCHEME}:/oauth2redirect?success=1"
        )
    except Exception:
        return RedirectResponse(
            url=f"{APP_DEEP_LINK_SCHEME}:/oauth2redirect?error=1"
        )


@router.get("/google/status")
async def check_google_drive_status(user_token: dict = Depends(require_no_temp_password_token)):
    """Verificar estado de autorización con Google Drive"""
    try:
        oauth_service = GoogleOAuthService()
        status = await oauth_service.check_user_drive_access(user_token['uid'])
        
        return status
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/google/revoke")
async def revoke_google_drive_access(user_token: dict = Depends(require_no_temp_password_token)):
    """Revocar acceso a Google Drive"""
    try:
        oauth_service = GoogleOAuthService()
        success = await oauth_service.revoke_user_access(user_token['uid'])
        
        if success:
            return {
                "message": "Acceso a Google Drive revocado exitosamente",
                "access_revoked": True
            }
        else:
            raise HTTPException(status_code=500, detail="Error revocando acceso")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/google/refresh")
async def refresh_google_drive_tokens(user_token: dict = Depends(require_no_temp_password_token)):
    """Renovar tokens de Google Drive"""
    try:
        oauth_service = GoogleOAuthService()
        credentials = await oauth_service.refresh_user_tokens(user_token['uid'])
        
        if credentials:
            return {
                "message": "Tokens renovados exitosamente",
                "access_token": credentials.token,
                "expires_at": credentials.expiry.isoformat() if credentials.expiry else None,
                "refreshed": True
            }
        else:
            raise HTTPException(status_code=400, detail="No se pudieron renovar los tokens")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/google/mobile-auth")
async def google_mobile_auth(
    payload: GoogleMobileAuthRequest,
    user_token: dict = Depends(require_no_temp_password_token),
):
    """
    Recibe los tokens de Google obtenidos desde la app móvil (flutter_appauth),
    los guarda en la base de datos y marca cloud_provider=google_drive.
    """
    try:
        user_id = user_token["uid"]

        # Guardar credenciales OAuth en la base de datos
        from app.services.autenticacion import OAuthCredentialsService

        oauth_service = OAuthCredentialsService()
        await oauth_service.upsert_user_credentials(
            user_id=user_id,
            provider="google",
            access_token=payload.access_token,
            refresh_token=payload.refresh_token,
            scopes=payload.scopes,
            expires_at=payload.expires_at,
        )

        # Marcar cloud_provider = google_drive en user_configs
        from app.models.user_config import CloudProvider, UserConfigUpdate
        from app.services.usuarios import UserConfigService

        config_service = UserConfigService()
        await config_service.get_or_create_user_config(user_id)
        update_data = UserConfigUpdate(cloud_provider=CloudProvider.GOOGLE_DRIVE)
        await config_service.update_user_config(user_id, update_data)

        return {"success": True, "message": "Google Drive vinculado correctamente"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error procesando autenticación móvil de Google: {str(e)}",
        )
