import logging
from typing import Any, Dict

from sqlalchemy.orm import Session

from app.models.user_config import CloudProvider, UserConfigUpdate
from app.services.almacenamiento import S3Service
from app.services.autenticacion import GoogleOAuthService
from app.services.subscription.subscription_service import SubscriptionService
from app.services.usuarios.user_config_service import UserConfigService

logger = logging.getLogger(__name__)
s3_singleton = S3Service()


class CloudStorageSetupService:
    def __init__(self, db: Session):
        self._db = db

    async def setup_storage(
        self,
        *,
        user_id: str,
        storage_type: str,
    ) -> Dict[str, Any]:
        if storage_type not in ("keepi_cloud", "google_drive", "not_configured"):
            raise ValueError("Tipo de almacenamiento no válido")

        cfg = UserConfigService(self._db)

        if storage_type == "not_configured":
            await cfg.get_or_create_user_config(user_id)
            await cfg.update_user_config(
                user_id, UserConfigUpdate(cloud_provider=CloudProvider.NOT_CONFIGURED)
            )
            return {
                "success": True,
                "message": "Almacenamiento restablecido a sin configurar",
                "storage_type": "not_configured",
            }

        if storage_type == "keepi_cloud":
            subscription_service = SubscriptionService()
            subscription = await subscription_service.get_user_subscription(
                user_id, self._db
            )
            status_value = (
                getattr(subscription.status, "value", subscription.status)
                if subscription
                else None
            )
            plan_code = None
            if subscription and subscription.plan_id:
                plan_code = SubscriptionService.resolve_plan_code(
                    self._db, subscription.plan_id
                )
            if not subscription or status_value != "active" or plan_code != "premium":
                raise PermissionError("SUBSCRIPTION_REQUIRED")

        await cfg.get_or_create_user_config(user_id)

        if storage_type == "keepi_cloud":
            await cfg.update_user_config(
                user_id, UserConfigUpdate(cloud_provider=CloudProvider.KEEPI_CLOUD)
            )
            result = await s3_singleton.create_user_folder(user_id)
            if not result.get("success"):
                raise RuntimeError("Error creando carpeta de usuario")

        if storage_type == "google_drive":
            oauth_service = GoogleOAuthService(self._db)
            credentials = await oauth_service.refresh_user_tokens(user_id)
            if not credentials:
                auth_data = await oauth_service.get_authorization_url(user_id)
                return {
                    "success": True,
                    "message": f"Almacenamiento configurado como {storage_type}",
                    "storage_type": storage_type,
                    "authorization_required": True,
                    "authorization_url": auth_data.get("authorization_url"),
                }
            await cfg.update_user_config(
                user_id, UserConfigUpdate(cloud_provider=CloudProvider.GOOGLE_DRIVE)
            )

        return {
            "success": True,
            "message": f"Almacenamiento configurado como {storage_type}",
            "storage_type": storage_type,
        }
