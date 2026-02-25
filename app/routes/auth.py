from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import Dict, Any, List, Optional

from app.core.security import verify_token, get_current_user
from app.services.autenticacion import GoogleOAuthService
from app.services.usuarios import UserService
from app.models.user import UserCreate, UserLogin, UserResponse
from app.models.user import User

router = APIRouter()


from pydantic import BaseModel
from datetime import datetime


class GoogleMobileAuthRequest(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    id_token: Optional[str] = None
    expires_at: Optional[datetime] = None
    token_type: Optional[str] = None
    scopes: Optional[List[str]] = None

@router.post("/register")
async def register_user(user_data: UserCreate):
    """Registrar nuevo usuario y devolver token de acceso"""
    try:
        if not user_data.password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Contraseña requerida para registro"
            )
        
        user_service = UserService()
        user = await user_service.create_user(user_data)
        
        # Generar token de acceso para autenticar automáticamente
        from datetime import timedelta
        from app.core.security import create_access_token
        
        access_token_expires = timedelta(minutes=30)
        access_token = create_access_token(
            data={
                "sub": str(user.id),
                "email": user.email,
                "name": user.name,
            },
            expires_delta=access_token_expires
        )

        # Devolver datos del usuario con el token
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "created_at": user.created_at.isoformat() if user.created_at else None
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
async def login_user(login_data: UserLogin):
    """Iniciar sesión de usuario"""
    try:
        user_service = UserService()
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
async def refresh_token(refresh_token: str):
    """Renovar token de acceso usando refresh token """
    try:
        from app.core.security import verify_refresh_token, create_access_token
        from app.services.usuarios import UserService
        
        # Verificar refresh token
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
        
        # Verificar que el usuario existe y el refresh token coincide
        user_service = UserService()
        user = user_service.get_user_orm_by_uid(user_id)

        if not user or user.refresh_token != refresh_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token inválido"
            )

        # Crear nuevo access token
        access_token = create_access_token({
            "sub": str(user.id),
            "email": user.email,
            "name": user.name,
        })
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": 30 * 60  # 30 minutos en segundos
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error renovando token: {str(e)}"
        )

@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """Obtener información del usuario actual"""
    return UserResponse.from_orm(current_user)

@router.get("/verify")
async def verify_authentication(user_token: dict = Depends(verify_token)):
    """Verificar token de autenticación"""
    return {
        "authenticated": True,
        "user_id": user_token['uid'],
        "email": user_token['email']
    }

@router.get("/current-user")
async def get_current_user(user_token: dict = Depends(verify_token)):
    """Obtener información del usuario actual"""
    try:
        from app.services.usuarios import UserService
        
        user_service = UserService()
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
async def authorize_google_drive(user_token: dict = Depends(verify_token)):
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

@router.get("/google/callback")
async def google_oauth_callback(
    code: str = Query(..., description="Código de autorización"),
    state: str = Query(..., description="Estado de la autorización")
):
    """Callback de OAuth2 para Google Drive - NO requiere autenticación"""
    try:
        oauth_service = GoogleOAuthService()
        
        # El state debe contener el user_id del usuario
        # Si no se puede extraer, usar un fallback
        user_id = None
        try:
            if state and state != "undefined":
                print(f"🔍 Intentando decodificar state: {state}")
                
                # Intentar decodificar el state para obtener el user_id
                import base64
                # Agregar padding si es necesario
                padding = 4 - (len(state) % 4)
                if padding != 4:
                    state += '=' * padding
                    print(f"🔍 State con padding: {state}")
                
                try:
                    user_id = base64.b64decode(state).decode('utf-8')
                    print(f"✅ User ID extraído del state: {user_id}")
                except UnicodeDecodeError as e:
                    print(f"⚠️ Error decodificando UTF-8: {e}")
                    # Intentar decodificar como bytes y luego a string
                    decoded_bytes = base64.b64decode(state)
                    user_id = decoded_bytes.decode('utf-8', errors='ignore')
                    print(f"✅ User ID extraído con fallback: {user_id}")
                    
            else:
                raise ValueError("State vacío o undefined")
        except Exception as e:
            print(f"⚠️ No se pudo extraer user_id del state: {e}")
            print(f"⚠️ State recibido: {state}")
            # Fallback: buscar en la base de datos por el código temporal
            user_id = await oauth_service.get_user_id_from_temp_code(code)
            if not user_id:
                user_id = "default_user"
            print(f"⚠️ Usando user_id por defecto para testing: {user_id}")
        
        tokens = await oauth_service.exchange_code_for_tokens(code, user_id)

        # Si la autorización fue exitosa, marcar al usuario como configurado con Google Drive
        try:
            if user_id and user_id != "default_user":
                from app.services.usuarios import UserConfigService
                from app.models.user_config import UserConfigUpdate, CloudProvider

                config_service = UserConfigService()
                await config_service.get_or_create_user_config(user_id)
                update_data = UserConfigUpdate(cloud_provider=CloudProvider.GOOGLE_DRIVE)
                await config_service.update_user_config(user_id, update_data)
        except Exception as cfg_err:
            # No romper el flujo de OAuth si falla solo la actualización de config
            print(f"⚠️ Error actualizando cloud_provider a google_drive para user_id={user_id}: {cfg_err}")
        
        return {
            "message": "Autorización exitosa",
            "access_granted": True,
            "user_id": tokens["user_id"],
            "scopes": tokens["scopes"],
            "expires_at": tokens["expires_at"]
        }
        
    except Exception as e:
        print(f"Error en callback de Google OAuth: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/google/status")
async def check_google_drive_status(user_token: dict = Depends(verify_token)):
    """Verificar estado de autorización con Google Drive"""
    try:
        oauth_service = GoogleOAuthService()
        status = await oauth_service.check_user_drive_access(user_token['uid'])
        
        return status
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/google/revoke")
async def revoke_google_drive_access(user_token: dict = Depends(verify_token)):
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
async def refresh_google_drive_tokens(user_token: dict = Depends(verify_token)):
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
    user_token: dict = Depends(verify_token),
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
        from app.services.usuarios import UserConfigService
        from app.models.user_config import UserConfigUpdate, CloudProvider

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
