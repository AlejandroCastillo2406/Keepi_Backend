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
        raise HTTPException(status_code=403, detail=str(e))
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error configurando almacenamiento")
        raise HTTPException(status_code=500, detail=MSG_ERROR_INTERNO)
