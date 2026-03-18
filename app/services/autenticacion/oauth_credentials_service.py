from datetime import datetime
from typing import Any, Dict, Optional

from google.oauth2.credentials import Credentials
from sqlalchemy.orm import Session

from app.models.oauth_credentials import OAuthCredentials


class OAuthCredentialsService:
    """Servicio para gestionar credenciales OAuth. Requiere db inyectado (Depends(get_db))."""

    def __init__(self, db: Session):
        self.db = db
    
    async def get_user_credentials(self, user_id: str, provider: str = "google") -> Optional[Dict[str, Any]]:
        """Obtener credenciales del usuario"""
        try:
            credentials = self.db.query(OAuthCredentials).filter(
                OAuthCredentials.user_id == user_id,
                OAuthCredentials.provider == provider
            ).first()
            
            if credentials:
                return {
                    'access_token': credentials.access_token,
                    'refresh_token': credentials.refresh_token,
                    'token_uri': credentials.token_uri,
                    'client_id': credentials.client_id,
                    'client_secret': credentials.client_secret,
                    'scopes': credentials.scopes or [],
                    'expires_at': credentials.expires_at.isoformat() if credentials.expires_at else None
                }
            return None
        except Exception as e:
            print(f"Error obteniendo credenciales: {e}")
            return None
    
    async def save_user_credentials(self, user_id: str, credentials: Credentials, provider: str = "google") -> bool:
        """Guardar credenciales del usuario"""
        try:
            # Verificar si ya existen credenciales
            existing = self.db.query(OAuthCredentials).filter(
                OAuthCredentials.user_id == user_id,
                OAuthCredentials.provider == provider
            ).first()
            
            if existing:
                # Actualizar credenciales existentes
                existing.access_token = credentials.token
                existing.refresh_token = credentials.refresh_token
                existing.expires_at = credentials.expiry
                existing.updated_at = datetime.now()
            else:
                # Crear nuevas credenciales
                new_credentials = OAuthCredentials(
                    user_id=user_id,
                    provider=provider,
                    access_token=credentials.token,
                    refresh_token=credentials.refresh_token,
                    token_uri=credentials.token_uri,
                    client_id=credentials.client_id,
                    client_secret=credentials.client_secret,
                    scopes=credentials.scopes,
                    expires_at=credentials.expiry
                )
                self.db.add(new_credentials)
            
            self.db.commit()
            return True
        except Exception as e:
            print(f"Error guardando credenciales: {e}")
            self.db.rollback()
            return False
    
    async def update_user_credentials(self, user_id: str, credentials: Credentials, provider: str = "google") -> bool:
        """Actualizar credenciales del usuario"""
        try:
            oauth_credentials = self.db.query(OAuthCredentials).filter(
                OAuthCredentials.user_id == user_id,
                OAuthCredentials.provider == provider
            ).first()
            
            if oauth_credentials:
                oauth_credentials.access_token = credentials.token
                oauth_credentials.refresh_token = credentials.refresh_token
                oauth_credentials.expires_at = credentials.expiry
                oauth_credentials.updated_at = datetime.now()
                
                self.db.commit()
                return True
            return False
        except Exception as e:
            print(f"Error actualizando credenciales: {e}")
            self.db.rollback()
            return False
    
    async def delete_user_credentials(self, user_id: str, provider: str = "google") -> bool:
        """Eliminar credenciales del usuario"""
        try:
            oauth_credentials = self.db.query(OAuthCredentials).filter(
                OAuthCredentials.user_id == user_id,
                OAuthCredentials.provider == provider
            ).first()
            
            if oauth_credentials:
                self.db.delete(oauth_credentials)
                self.db.commit()
                return True
            return False
        except Exception as e:
            print(f"Error eliminando credenciales: {e}")
            self.db.rollback()
            return False
