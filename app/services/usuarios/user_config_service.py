import logging
from typing import Optional, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session

from app.models.user_config import UserConfig, UserConfigCreate, UserConfigUpdate, UserConfigResponse, CloudProvider, CloudProviderInfo

logger = logging.getLogger(__name__)


class UserConfigService:
    def __init__(self, db: Session):
        self.db = db
    
    async def get_user_config(self, user_id: str) -> Optional[UserConfigResponse]:
        """Obtener configuración del usuario"""
        try:
            config = self.db.query(UserConfig).filter(UserConfig.user_id == user_id).first()
            if config:
                return UserConfigResponse.from_orm(config)
            return None
            
        except Exception as e:
            logger.error(f"Error obteniendo configuración de usuario: {str(e)}")
            raise
    
    async def create_user_config(self, user_id: str, config_data: UserConfigCreate) -> UserConfigResponse:
        """Crear configuración de usuario"""
        try:
            # Crear instancia de configuración
            config = UserConfig(
                user_id=user_id,
                cloud_provider=config_data.cloud_provider.value,
                notification_preferences=config_data.notification_preferences or {}
            )
            
            self.db.add(config)
            self.db.commit()
            self.db.refresh(config)
            
            return UserConfigResponse.from_orm(config)
            
        except Exception as e:
            logger.error(f"Error creando configuración de usuario: {str(e)}")
            self.db.rollback()
            raise
    
    async def update_user_config(self, user_id: str, config_data: UserConfigUpdate) -> Optional[UserConfigResponse]:
        """Actualizar configuración de usuario"""
        try:
            config = self.db.query(UserConfig).filter(UserConfig.user_id == user_id).first()
            
            if not config:
                return None
            
            # Actualizar campos
            if config_data.cloud_provider is not None:
                config.cloud_provider = config_data.cloud_provider.value
            
            if config_data.notification_preferences is not None:
                config.notification_preferences = config_data.notification_preferences
            
            # Guardar cambios
            self.db.commit()
            self.db.refresh(config)
            
            return UserConfigResponse.from_orm(config)
            
        except Exception as e:
            logger.error(f"Error actualizando configuración de usuario: {str(e)}")
            self.db.rollback()
            raise
    
    async def get_or_create_user_config(self, user_id: str) -> UserConfigResponse:
        """Obtener o crear configuración de usuario por defecto"""
        try:
            config = await self.get_user_config(user_id)
            
            if not config:
                # Crear configuración por defecto: sin configurar (primera vez)
                default_config = UserConfigCreate(
                    cloud_provider=CloudProvider.NOT_CONFIGURED,
                    notification_preferences={}
                )
                config = await self.create_user_config(user_id, default_config)
            
            return config
            
        except Exception as e:
            logger.error(f"Error obteniendo/creando configuración de usuario: {str(e)}")
            raise
    
    async def get_available_cloud_providers(self) -> list[CloudProviderInfo]:
        """Obtener proveedores de nube disponibles"""
        try:
            providers = [
                CloudProviderInfo(
                    provider=CloudProvider.GOOGLE_DRIVE,
                    name="Google Drive",
                    description="Almacenamiento en tu cuenta personal de Google Drive",
                    features=[
                        "Integración con Google Workspace",
                        "Acceso desde cualquier dispositivo",
                        "Colaboración en tiempo real",
                        "15GB de almacenamiento gratuito"
                    ],
                    storage_limit="15GB (gratuito)",
                    is_available=True
                ),
                CloudProviderInfo(
                    provider=CloudProvider.KEEPI_CLOUD,
                    name="Keepi Cloud",
                    description="Almacenamiento seguro en la nube de Keepi (AWS S3)",
                    features=[
                        "Almacenamiento dedicado por usuario",
                        "Categorización automática con IA",
                        "Análisis avanzado de documentos",
                        "Carpetas organizadas automáticamente"
                    ],
                    storage_limit="1GB (gratuito)",
                    is_available=True
                )
            ]
            
            return providers
            
        except Exception as e:
            logger.error(f"Error obteniendo proveedores de nube: {str(e)}")
            raise
    
    async def switch_cloud_provider(self, user_id: str, new_provider: CloudProvider) -> UserConfigResponse:
        """Cambiar proveedor de nube del usuario"""
        try:
            config_update = UserConfigUpdate(cloud_provider=new_provider)
            updated_config = await self.update_user_config(user_id, config_update)
            
            if not updated_config:
                raise ValueError("No se pudo actualizar la configuración del usuario")
            
            # Aquí podrías agregar lógica adicional para migrar documentos
            # entre proveedores si es necesario
            
            return updated_config
            
        except Exception as e:
            logger.error(f"Error cambiando proveedor de nube: {str(e)}")
            raise
