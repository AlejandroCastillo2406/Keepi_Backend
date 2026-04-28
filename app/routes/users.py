from typing import List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.security import get_current_user
from app.factories.user_factory import get_user_service
from app.models.user import User, UserResponse, UserUpdate
from app.services.autenticacion.jwt_inspection_service import JwtInspectionService
from app.services.usuarios.user_service import UserService

router = APIRouter()


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service),
):
    u = await user_service.get_me_response(str(current_user.id))
    if not u:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return u


@router.get("/debug-token")
async def debug_token(
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer(auto_error=False)),
):
    return JwtInspectionService.decode_bearer_optional(credentials)


@router.get("/profile", response_model=UserResponse)
async def get_user_profile(
    current_user: User = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service),
):
    u = await user_service.get_me_response(str(current_user.id))
    if not u:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return u


@router.put("/profile", response_model=UserResponse)
async def update_user_profile(
    user_data: UserUpdate,
    current_user: User = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service),
):
    try:
        updated_user = await user_service.update_user(str(current_user.id), user_data)
        if updated_user:
            return updated_user
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/all", response_model=List[UserResponse])
async def get_all_users(user_service: UserService = Depends(get_user_service)):
    try:
        return await user_service.get_all_users()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{user_uid}", response_model=UserResponse)
async def get_user_by_uid(
    user_uid: str, user_service: UserService = Depends(get_user_service)
):
    try:
        user = await user_service.get_user_by_uid(user_uid)
        if user:
            return user
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
