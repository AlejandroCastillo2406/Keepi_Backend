from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_no_temp_password_token
from app.models.user_config import UserConfigResponse
from app.services.usuarios import UserConfigService

router = APIRouter()


@router.get("/", response_model=UserConfigResponse)
async def get_user_config(
    user_token: dict = Depends(require_no_temp_password_token),
    db: Session = Depends(get_db),
):
    """Obtener configuración del usuario (cloud_provider). Usado por el front."""
    try:
        config_service = UserConfigService(db)
        config = await config_service.get_or_create_user_config(user_token["uid"])
        return config
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
