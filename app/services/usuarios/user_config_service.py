import logging
import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.models.user_config import (
    CloudProvider,
    CloudProviderInfo,
    UserConfig,
    UserConfigCreate,
    UserConfigResponse,
    UserConfigUpdate,
)
from app.repositories.user_config_repository import UserConfigRepository
from app.services.almacenamiento import S3Service

logger = logging.getLogger(__name__)
_s3 = S3Service()


class UserConfigService:
    def __init__(
        self,
        db: Session,
        user_config_repository: UserConfigRepository | None = None,
    ):
        self.db = db
        self._repo = user_config_repository or UserConfigRepository(db)

    def _uid(self, user_id: str) -> uuid.UUID:
        return uuid.UUID(str(user_id))

    async def get_user_config(self, user_id: str) -> Optional[UserConfigResponse]:
        try:
            row = self._repo.get_by_user_id(user_id)
            if row:
                return UserConfigResponse.from_orm(row)
            return None
        except Exception as e:
            logger.error("Error obteniendo configuración de usuario: %s", e)
            raise

    async def create_user_config(
        self, user_id: str, config_data: UserConfigCreate
    ) -> UserConfigResponse:
        try:
            row = UserConfig(
                user_id=self._uid(user_id),
                cloud_provider=config_data.cloud_provider.value,
                notification_preferences=config_data.notification_preferences or {},
            )
            self._repo.add(row)
            return UserConfigResponse.from_orm(row)
        except Exception as e:
            logger.error("Error creando configuración de usuario: %s", e)
            self.db.rollback()
            raise

    async def update_user_config(
        self, user_id: str, config_data: UserConfigUpdate
    ) -> Optional[UserConfigResponse]:
        try:
            config = self._repo.get_by_user_id(user_id)
            if not config:
                return None
            if config_data.cloud_provider is not None:
                config.cloud_provider = config_data.cloud_provider.value
            if config_data.notification_preferences is not None:
                config.notification_preferences = config_data.notification_preferences
            self._repo.save(config)
            return UserConfigResponse.from_orm(config)
        except Exception as e:
            logger.error("Error actualizando configuración de usuario: %s", e)
            self.db.rollback()
            raise

    async def _provision_keepi_cloud_folder(self, user_id: str) -> None:
        try:
            result = await _s3.create_user_folder(user_id)
            if not result.get("success"):
                logger.warning(
                    "Carpeta S3 no creada para usuario %s: %s", user_id, result
                )
        except Exception:
            logger.exception("Error creando carpeta S3 para usuario %s", user_id)

    async def _activate_keepi_cloud_default(
        self, user_id: str
    ) -> UserConfigResponse:
        updated = await self.update_user_config(
            user_id, UserConfigUpdate(cloud_provider=CloudProvider.KEEPI_CLOUD)
        )
        if not updated:
            raise ValueError("No se pudo activar Keepi Cloud por defecto")
        await self._provision_keepi_cloud_folder(user_id)
        return updated

    async def get_or_create_user_config(self, user_id: str) -> UserConfigResponse:
        try:
            config = await self.get_user_config(user_id)
            if not config:
                default_config = UserConfigCreate(
                    cloud_provider=CloudProvider.KEEPI_CLOUD,
                    notification_preferences={},
                )
                config = await self.create_user_config(user_id, default_config)
                await self._provision_keepi_cloud_folder(user_id)
            elif config.cloud_provider == CloudProvider.NOT_CONFIGURED:
                config = await self._activate_keepi_cloud_default(user_id)
            return config
        except Exception as e:
            logger.error("Error obteniendo/creando configuración de usuario: %s", e)
            raise

    async def get_available_cloud_providers(self) -> list[CloudProviderInfo]:
        try:
            return [
                CloudProviderInfo(
                    provider=CloudProvider.GOOGLE_DRIVE,
                    name="Google Drive",
                    description="Almacenamiento en tu cuenta personal de Google Drive",
                    features=[
                        "Integración con Google Workspace",
                        "Acceso desde cualquier dispositivo",
                        "Colaboración en tiempo real",
                        "15GB de almacenamiento gratuito",
                    ],
                    storage_limit="15GB (gratuito)",
                    is_available=True,
                ),
                CloudProviderInfo(
                    provider=CloudProvider.KEEPI_CLOUD,
                    name="Keepi Cloud",
                    description="Almacenamiento seguro en la nube de Keepi (AWS S3)",
                    features=[
                        "Almacenamiento dedicado por usuario",
                        "Categorización automática con IA",
                        "Análisis avanzado de documentos",
                        "Carpetas organizadas automáticamente",
                    ],
                    storage_limit="1GB (gratuito)",
                    is_available=True,
                ),
            ]
        except Exception as e:
            logger.error("Error obteniendo proveedores de nube: %s", e)
            raise

    async def switch_cloud_provider(
        self, user_id: str, new_provider: CloudProvider
    ) -> UserConfigResponse:
        try:
            updated = await self.update_user_config(
                user_id, UserConfigUpdate(cloud_provider=new_provider)
            )
            if not updated:
                raise ValueError("No se pudo actualizar la configuración del usuario")
            return updated
        except Exception as e:
            logger.error("Error cambiando proveedor de nube: %s", e)
            raise
