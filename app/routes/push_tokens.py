from fastapi import APIRouter, Depends

from app.core.security import require_no_temp_password_user
from app.models.user import User
from app.models.user_device_token import (
    RegisterDeviceTokenRequest,
    RegisterDeviceTokenResponse,
)
from app.factories.user_factory import get_push_token_service
from app.services.usuarios.push_token_service import PushTokenService

router = APIRouter()


@router.post("/register", response_model=RegisterDeviceTokenResponse)
async def register_push_token(
    body: RegisterDeviceTokenRequest,
    current_user: User = Depends(require_no_temp_password_user),
    svc: PushTokenService = Depends(get_push_token_service),
):
    return svc.register_token(current_user.id, body)
