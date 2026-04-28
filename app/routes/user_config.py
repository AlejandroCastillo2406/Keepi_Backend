from fastapi import APIRouter, Depends, HTTPException
from app.core.security import require_no_temp_password_token
from app.factories.user_factory import get_user_config_service
from app.models.user_config import UserConfigResponse
from app.services.usuarios.user_config_service import UserConfigService

router = APIRouter()


@router.get("/", response_model=UserConfigResponse)
async def get_user_config(
    user_token: dict = Depends(require_no_temp_password_token),
    config_service: UserConfigService = Depends(get_user_config_service),
):
    try:
        config = await config_service.get_or_create_user_config(user_token["uid"])
        return config
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
