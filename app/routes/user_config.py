from fastapi import APIRouter, Depends, HTTPException

from app.core.security import verify_token
from app.services.usuarios import UserConfigService
from app.models.user_config import UserConfigResponse

router = APIRouter()


@router.get("/", response_model=UserConfigResponse)
async def get_user_config(user_token: dict = Depends(verify_token)):
    """Obtener configuración del usuario (cloud_provider). Usado por el front."""
    try:
        config_service = UserConfigService()
        config = await config_service.get_or_create_user_config(user_token["uid"])
        return config
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
