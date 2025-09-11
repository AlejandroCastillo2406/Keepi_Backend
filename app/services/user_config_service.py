import logging
from typing import Optional, Dict, Any
from datetime import datetime
import firebase_admin
from firebase_admin import firestore

from app.models.user_config import UserConfigCreate, UserConfigUpdate, UserConfigResponse, CloudProvider, CloudProviderInfo

logger = logging.getLogger(__name__)

class UserConfigService:
    def __init__(self):
        self.db = firestore.client()
        self.collection = "user_configs"
    
    async def get_user_config(self, user_id: str) -> Optional[UserConfigResponse]:
        """Obtener configuración del usuario"""
        try:
            doc_ref = self.db.collection(self.collection).document(user_id)
            doc = doc_ref.get()
            
            if doc.exists:
                data = doc.to_dict()
                return UserConfigResponse(
                    id=doc.id,
                    user_id=user_id,
                    cloud_provider=data.get('cloud_provider', CloudProvider.GOOGLE_DRIVE),
                    auto_categorization=data.get('auto_categorization', True),
                    aws_analysis_enabled=data.get('aws_analysis_enabled', True),
                    notification_preferences=data.get('notification_preferences', {}),
                    created_at=data.get('created_at', datetime.utcnow()),
                    updated_at=data.get('updated_at', datetime.utcnow())
                )
            return None
            
        except Exception as e:
            logger.error(f"Error obteniendo configuración de usuario: {str(e)}")
            raise
    
    async def create_user_config(self, user_id: str, config_data: UserConfigCreate) -> UserConfigResponse:
        """Crear configuración de usuario"""
        try:
            now = datetime.utcnow()
            
            config_dict = {
                'user_id': user_id,
                'cloud_provider': config_data.cloud_provider.value,
                'auto_categorization': config_data.auto_categorization,
                'aws_analysis_enabled': config_data.aws_analysis_enabled,
                'notification_preferences': config_data.notification_preferences or {},
                'created_at': now,
                'updated_at': now
            }
            
            doc_ref = self.db.collection(self.collection).document(user_id)
            doc_ref.set(config_dict)
            
            return UserConfigResponse(
                id=user_id,
                user_id=user_id,
                cloud_provider=config_data.cloud_provider,
                auto_categorization=config_data.auto_categorization,
                aws_analysis_enabled=config_data.aws_analysis_enabled,
                notification_preferences=config_data.notification_preferences or {},
                created_at=now,
                updated_at=now
            )
            
        except Exception as e:
            logger.error(f"Error creando configuración de usuario: {str(e)}")
            raise
    
    async def update_user_config(self, user_id: str, config_data: UserConfigUpdate) -> Optional[UserConfigResponse]:
        """Actualizar configuración de usuario"""
        try:
            doc_ref = self.db.collection(self.collection).document(user_id)
            doc = doc_ref.get()
            
            if not doc.exists:
                return None
            
            # Preparar datos de actualización
            update_data = {'updated_at': datetime.utcnow()}
            
            if config_data.cloud_provider is not None:
                update_data['cloud_provider'] = config_data.cloud_provider.value
            
            if config_data.auto_categorization is not None:
                update_data['auto_categorization'] = config_data.auto_categorization
            
            if config_data.aws_analysis_enabled is not None:
                update_data['aws_analysis_enabled'] = config_data.aws_analysis_enabled
            
            if config_data.notification_preferences is not None:
                update_data['notification_preferences'] = config_data.notification_preferences
            
            # Actualizar documento
            doc_ref.update(update_data)
            
            # Obtener configuración actualizada
            return await self.get_user_config(user_id)
            
        except Exception as e:
            logger.error(f"Error actualizando configuración de usuario: {str(e)}")
            raise
    
    async def get_or_create_user_config(self, user_id: str) -> UserConfigResponse:
        """Obtener o crear configuración de usuario por defecto"""
        try:
            config = await self.get_user_config(user_id)
            
            if not config:
                # Crear configuración por defecto
                default_config = UserConfigCreate(
                    cloud_provider=CloudProvider.GOOGLE_DRIVE,
                    auto_categorization=True,
                    aws_analysis_enabled=True,
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
