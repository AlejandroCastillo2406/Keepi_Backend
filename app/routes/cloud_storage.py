import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_no_temp_password_user
from app.factories.cloud_storage_factory import get_cloud_storage_setup_service
from app.models.user import User
from app.services.almacenamiento.cloud_storage_setup_service import (
    CloudStorageSetupService,
)
from app.services.subscription.subscription_service import SubscriptionService

router = APIRouter()
logger = logging.getLogger(__name__)
MSG_ERROR_INTERNO = "Error interno del servidor"


class SetupCloudStorageRequest(BaseModel):
    storage_type: str

    class Config:
        json_schema_extra = {"example": {"storage_type": "keepi_cloud"}}


@router.post("/setup-cloud-storage")
async def setup_cloud_storage(
    request: SetupCloudStorageRequest,
    current_user: User = Depends(require_no_temp_password_user),
    db: Session = Depends(get_db),
    svc: CloudStorageSetupService = Depends(get_cloud_storage_setup_service),
):
    try:
        return await svc.setup_storage(
            user_id=str(current_user.id),
            storage_type=request.storage_type,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        if str(e) == "SUBSCRIPTION_REQUIRED":
            subscription_service = SubscriptionService()
            subscription = await subscription_service.get_user_subscription(
                str(current_user.id), db
            )
            status_value = (
                getattr(subscription.status, "value", subscription.status)
                if subscription
                else None
            )
            plan_code = None
            if subscription and subscription.plan_id:
                plan_code = SubscriptionService.resolve_plan_code(
                    db, subscription.plan_id
                )
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
        raise HTTPException(status_code=403, detail=str(e))
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error configurando almacenamiento")
        raise HTTPException(status_code=500, detail=MSG_ERROR_INTERNO)
