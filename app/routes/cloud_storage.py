import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import UserResponse
from app.models.user_config import CloudProvider, UserConfigUpdate
from app.models.plans import Plan
from app.services.almacenamiento import S3Service
from app.services.autenticacion import GoogleOAuthService
from app.services.subscription import SubscriptionService
from app.services.usuarios import UserConfigService

router = APIRouter()
logger = logging.getLogger(__name__)
s3_service = S3Service()
MSG_ERROR_INTERNO = "Error interno del servidor"

# Modelo para el request de configuración de almacenamiento
class SetupCloudStorageRequest(BaseModel):
    storage_type: str  # "keepi_cloud" | "google_drive" | "not_configured"

    class Config:
        json_schema_extra = {"example": {"storage_type": "keepi_cloud"}}


@router.post("/setup-cloud-storage")
async def setup_cloud_storage(
    request: SetupCloudStorageRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Configura el tipo de almacenamiento: keepi_cloud (requiere pago Stripe),
    google_drive (OAuth) o not_configured (p. ej. si se cancela el pago).
    """
    try:
        logger.debug("Recibiendo request setup-cloud-storage: %s", request)
        storage_type = request.storage_type

        if not storage_type or storage_type not in ["keepi_cloud", "google_drive", "not_configured"]:
            logger.warning("Tipo de almacenamiento no válido: %s", storage_type)
            raise HTTPException(status_code=400, detail="Tipo de almacenamiento no válido")

        if storage_type == "not_configured":
            try:
                config_service = UserConfigService(db)
                await config_service.get_or_create_user_config(str(current_user.id))
                update_data = UserConfigUpdate(cloud_provider=CloudProvider.NOT_CONFIGURED)
                await config_service.update_user_config(str(current_user.id), update_data)
                logger.info("cloud_provider actualizado a not_configured para usuario %s", current_user.id)
                return {
                    "success": True,
                    "message": "Almacenamiento restablecido a sin configurar",
                    "storage_type": "not_configured",
                }
            except Exception:
                logger.exception("Error actualizando a not_configured")
                raise HTTPException(status_code=500, detail=MSG_ERROR_INTERNO)

        if storage_type == "keepi_cloud":
            logger.debug("Validando suscripción Keepi Cloud para usuario %s", current_user.id)
            try:
                subscription_service = SubscriptionService()
                subscription = await subscription_service.get_user_subscription(str(current_user.id), db)
                status_value = getattr(subscription.status, "value", subscription.status) if subscription else None
                plan_code = None
                if subscription and subscription.plan_id:
                    try:
                        plan_id_uuid = uuid.UUID(subscription.plan_id)
                    except (ValueError, TypeError):
                        plan_id_uuid = None
                    if plan_id_uuid:
                        plan = db.query(Plan).filter(Plan.id == plan_id_uuid).first()
                        if plan and plan.code:
                            plan_code = plan.code

                if not subscription or status_value != "active" or plan_code != "premium":
                    logger.warning("Suscripción no válida para Keepi Cloud - usuario %s", current_user.id)
                    raise HTTPException(
                        status_code=402,
                        detail={
                            "error": "subscription_required",
                            "message": "Se requiere una suscripción activa para usar Keepi Cloud",
                            "subscription_info": {
                                "required_plan": "premium",
                                "current_plan": plan_code if plan_code else "none",
                                "current_status": status_value if subscription else "none",
                            },
                        },
                    )
                logger.debug("Suscripción activa para usuario %s", current_user.id)
            except HTTPException:
                raise
            except Exception:
                logger.exception("Error validando suscripción")
                raise HTTPException(status_code=500, detail=MSG_ERROR_INTERNO)

        logger.debug("Preparando configuración de almacenamiento para usuario %s", current_user.id)
        try:
            config_service = UserConfigService(db)
            user_config = await config_service.get_or_create_user_config(str(current_user.id))
            if storage_type == "keepi_cloud":
                update_data = UserConfigUpdate(cloud_provider=CloudProvider.KEEPI_CLOUD)
                await config_service.update_user_config(str(current_user.id), update_data)
                logger.info("cloud_provider actualizado a keepi_cloud para usuario %s", current_user.id)
        except Exception:
            logger.exception("Error preparando/actualizando cloud_provider")
            raise HTTPException(status_code=500, detail=MSG_ERROR_INTERNO)

        if storage_type == "keepi_cloud":
            result = await s3_service.create_user_folder(str(current_user.id))
            if not result.get("success"):
                raise HTTPException(status_code=500, detail="Error creando carpeta de usuario")

        if storage_type == "google_drive":
            oauth_service = GoogleOAuthService(db)
            credentials = await oauth_service.refresh_user_tokens(str(current_user.id))
            if not credentials:
                auth_data = await oauth_service.get_authorization_url(str(current_user.id))
                return {
                    "success": True,
                    "message": f"Almacenamiento configurado como {storage_type}",
                    "storage_type": storage_type,
                    "authorization_required": True,
                    "authorization_url": auth_data.get("authorization_url"),
                }
            update_data = UserConfigUpdate(cloud_provider=CloudProvider.GOOGLE_DRIVE)
            await config_service.update_user_config(str(current_user.id), update_data)
            logger.info("cloud_provider actualizado a google_drive para usuario %s", current_user.id)

        return {
            "success": True,
            "message": f"Almacenamiento configurado como {storage_type}",
            "storage_type": storage_type,
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error configurando almacenamiento")
        raise HTTPException(status_code=500, detail=MSG_ERROR_INTERNO)
