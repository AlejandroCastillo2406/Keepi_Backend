from typing import Dict, Any, Optional
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
import json
import os
from datetime import datetime, timedelta
from app.config.settings import settings
import base64

class GoogleOAuthService:
    """Servicio para manejar autenticación OAuth2 con Google"""
    
    def __init__(self):
        # Configuración OAuth2 desde variables de entorno
        self.client_secrets_file = settings.google_client_secrets_path
        self.scopes = [
            'openid',
            'https://www.googleapis.com/auth/drive.file',
            'https://www.googleapis.com/auth/drive.metadata.readonly',
            'https://www.googleapis.com/auth/userinfo.email'
        ]
        # URL de callback desde variables de entorno
        self.redirect_uri = settings.google_redirect_uri or f"{settings.host}/api/v1/auth/google/callback"
    
    async def get_authorization_url(self, user_id: str) -> Dict[str, str]:
        """Generar URL de autorización para Google Drive"""
        try:
            flow = Flow.from_client_secrets_file(
                self.client_secrets_file,
                scopes=self.scopes,
                redirect_uri=self.redirect_uri
            )
            
            # Generar state personalizado con el user_id
            state = base64.b64encode(user_id.encode('utf-8')).decode('utf-8')
            
            # Configurar el state en el flow
            flow.state = state
            
            authorization_url, _ = flow.authorization_url(
                access_type='offline',
                include_granted_scopes='true',
                prompt='consent',  # Usar solo 'prompt' en lugar de 'approval_prompt'
                state=state,  # Pasar el state explícitamente
                login_hint=None  # Permitir que el usuario elija cuenta
            )
            
            print(f"🔐 URL de autorización generada para usuario: {user_id}")
            print(f"🔐 State configurado: {state}")
            print(f"🔐 URL completa: {authorization_url}")
            
            return {
                "authorization_url": authorization_url,
                "state": state
            }
            
        except Exception as e:
            print(f"Error generando URL de autorización: {e}")
            raise
    
    async def exchange_code_for_tokens(self, authorization_code: str, user_id: str) -> Dict[str, Any]:
        """Intercambiar código de autorización por tokens"""
        try:
            # Crear nuevo flow para intercambiar tokens
            flow = Flow.from_client_secrets_file(
                self.client_secrets_file,
                scopes=self.scopes,
                redirect_uri=self.redirect_uri
            )
            
            # Intercambiar código por tokens
            flow.fetch_token(code=authorization_code)
            
            credentials = flow.credentials
            
            # Usar el user_id que se pasa como parámetro
            if not user_id:
                user_id = "default_user"
                print("⚠️ Usando user_id por defecto para testing")
            
            print(f"✅ Guardando credenciales para usuario: {user_id}")
            
            # Guardar credenciales en Firestore
            await self._save_user_credentials(user_id, credentials)
            
            return {
                "access_token": credentials.token,
                "refresh_token": credentials.refresh_token,
                "expires_at": credentials.expiry.isoformat() if credentials.expiry else None,
                "scopes": credentials.scopes,
                "user_id": user_id
            }
            
        except Exception as e:
            print(f"Error intercambiando código por tokens: {e}")
            raise
    
    async def refresh_user_tokens(self, user_id: str) -> Optional[Credentials]:
        """Refrescar tokens del usuario"""
        try:
            # Obtener credenciales guardadas
            credentials_data = await self._get_user_credentials(user_id)
            
            if not credentials_data:
                return None
            
            credentials = Credentials(
                token=credentials_data.get('access_token'),
                refresh_token=credentials_data.get('refresh_token'),
                token_uri="https://oauth2.googleapis.com/token",
                client_id=credentials_data.get('client_id'),
                client_secret=credentials_data.get('client_secret'),
                scopes=credentials_data.get('scopes', self.scopes)
            )
            
            # Siempre intentar refrescar si hay refresh_token
            if credentials.refresh_token:
                try:
                    credentials.refresh(Request())
                    print(f"✅ Token refrescado exitosamente para usuario: {user_id}")
                    
                    # Actualizar tokens en Firestore
                    await self._update_user_credentials(user_id, credentials)
                    print(f"✅ Credenciales actualizadas en Firestore para usuario: {user_id}")
                except Exception as refresh_error:
                    print(f"❌ Error refrescando token: {refresh_error}")
                    return None
            else:
                print(f"❌ No hay refresh_token disponible para usuario: {user_id}")
                return None
            
            return credentials
            
        except Exception as e:
            print(f"Error refrescando tokens: {e}")
            return None
    
    async def revoke_user_access(self, user_id: str) -> bool:
        """Revocar acceso del usuario a Google Drive"""
        try:
            # Eliminar credenciales de Firestore
            await self._delete_user_credentials(user_id)
            return True
            
        except Exception as e:
            print(f"Error revocando acceso: {e}")
            return False
    
    async def check_user_drive_access(self, user_id: str) -> Dict[str, Any]:
        """Verificar si el usuario tiene acceso a Google Drive con verificación activa"""
        try:
            credentials_data = await self._get_user_credentials(user_id)
            
            if not credentials_data:
                return {
                    "has_access": False,
                    "status": "no_credentials",
                    "message": "Usuario no ha autorizado acceso a Google Drive",
                    "requires_action": "authorize"
                }
            
            # Verificar si el token ha expirado
            expires_at = credentials_data.get('expires_at')
            current_time = datetime.now()
            
            if expires_at:
                try:
                    expiry_time = datetime.fromisoformat(expires_at)
                    # Asegurar que ambas fechas tengan la misma zona horaria
                    if expiry_time.tzinfo is not None:
                        expiry_time = expiry_time.replace(tzinfo=None)
                    if current_time.tzinfo is not None:
                        current_time = current_time.replace(tzinfo=None)
                    
                    time_until_expiry = expiry_time - current_time
                except Exception as e:
                    print(f"Error procesando fecha de expiración: {e}")
                    # Si hay error con la fecha, asumir que está expirado
                    return {
                        "has_access": False,
                        "status": "error",
                        "message": f"Error verificando acceso: {str(e)}",
                        "requires_action": "authorize"
                    }
                
                # Si el token expira en menos de 5 minutos, considerarlo como expirado
                if time_until_expiry.total_seconds() < 300:  # 5 minutos
                    return {
                        "has_access": False,
                        "status": "expired",
                        "message": "Token expirado o próximo a expirar, requiere renovación",
                        "expires_at": expires_at,
                        "time_until_expiry": time_until_expiry.total_seconds(),
                        "requires_action": "refresh"
                    }
            
            # Intentar refrescar el token para verificar que sigue siendo válido
            try:
                credentials = Credentials(
                    token=credentials_data.get('access_token'),
                    refresh_token=credentials_data.get('refresh_token'),
                    token_uri="https://oauth2.googleapis.com/token",
                    client_id=credentials_data.get('client_id'),
                    client_secret=credentials_data.get('client_secret'),
                    scopes=credentials_data.get('scopes', self.scopes)
                )
                
                # Si el token está expirado, intentar refrescarlo
                if credentials.expired and credentials.refresh_token:
                    credentials.refresh(Request())
                    await self._update_user_credentials(user_id, credentials)
                
                return {
                    "has_access": True,
                    "status": "active",
                    "message": "Usuario tiene acceso activo a Google Drive",
                    "scopes": credentials_data.get('scopes', []),
                    "expires_at": credentials.expiry.isoformat() if credentials.expiry else expires_at,
                    "requires_action": "none"
                }
                
            except Exception as refresh_error:
                print(f"Error refrescando token: {refresh_error}")
                return {
                    "has_access": False,
                    "status": "invalid_credentials",
                    "message": "Credenciales inválidas, requiere reautorización",
                    "requires_action": "authorize"
                }
            
        except Exception as e:
            print(f"Error verificando acceso: {e}")
            return {
                "has_access": False,
                "status": "error",
                "message": f"Error verificando acceso: {str(e)}",
                "requires_action": "authorize"
            }
    
    async def get_user_id_from_temp_code(self, code: str) -> Optional[str]:
        """Obtener user_id desde un código de autorización temporal"""
        try:
            # Crear un flow temporal para obtener información del código
            flow = Flow.from_client_secrets_file(
                self.client_secrets_file,
                scopes=self.scopes,
                redirect_uri=self.redirect_uri
            )
            
            # Intentar obtener tokens para extraer información
            flow.fetch_token(code=code)
            credentials = flow.credentials
            
            # Por ahora, retornar None ya que no podemos extraer user_id del código
            # En una implementación real, podrías usar un cache temporal o base de datos
            print(f"🔍 Código de autorización recibido: {code[:10]}...")
            print(f"🔍 Scopes obtenidos: {credentials.scopes}")
            
            return None
            
        except Exception as e:
            print(f"⚠️ Error obteniendo user_id del código temporal: {e}")
            return None

    async def _save_user_credentials(self, user_id: str, credentials: Credentials) -> bool:
        """Guardar credenciales del usuario en PostgreSQL"""
        try:
            from app.services.oauth_credentials_service import OAuthCredentialsService
            
            oauth_service = OAuthCredentialsService()
            success = await oauth_service.save_user_credentials(user_id, credentials)
            
            if success:
                print(f"✅ Credenciales guardadas para usuario: {user_id}")
            return success
            
        except Exception as e:
            print(f"Error guardando credenciales: {e}")
            return False
    
    async def _get_user_credentials(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Obtener credenciales del usuario desde PostgreSQL"""
        try:
            from app.services.oauth_credentials_service import OAuthCredentialsService
            
            oauth_service = OAuthCredentialsService()
            return await oauth_service.get_user_credentials(user_id)
            
        except Exception as e:
            print(f"Error obteniendo credenciales: {e}")
            return None
    
    async def _update_user_credentials(self, user_id: str, credentials: Credentials) -> bool:
        """Actualizar credenciales del usuario en PostgreSQL"""
        try:
            from app.services.oauth_credentials_service import OAuthCredentialsService
            
            oauth_service = OAuthCredentialsService()
            return await oauth_service.update_user_credentials(user_id, credentials)
            
        except Exception as e:
            print(f"Error actualizando credenciales: {e}")
            return False
    
    async def _delete_user_credentials(self, user_id: str) -> bool:
        """Eliminar credenciales del usuario de PostgreSQL"""
        try:
            from app.services.oauth_credentials_service import OAuthCredentialsService
            
            oauth_service = OAuthCredentialsService()
            return await oauth_service.delete_user_credentials(user_id)
            
        except Exception as e:
            print(f"Error eliminando credenciales: {e}")
            return False
