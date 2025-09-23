from fastapi import APIRouter, Depends, HTTPException, status
from typing import List

from app.utils.auth import get_current_user
from app.services.user_service import UserService
from app.models.user import UserCreate, UserUpdate, UserResponse, UserSettings, User

router = APIRouter()

@router.get("/profile", response_model=UserResponse)
async def get_user_profile(current_user: User = Depends(get_current_user)):
    """Obtener perfil del usuario autenticado"""
    return UserResponse.from_orm(current_user)

@router.put("/profile", response_model=UserResponse)
async def update_user_profile(
    user_data: UserUpdate,
    current_user: User = Depends(get_current_user)
):
    """Actualizar perfil del usuario"""
    try:
        user_service = UserService()
        updated_user = await user_service.update_user(str(current_user.id), user_data)
        
        if updated_user:
            return updated_user
        else:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/settings")
async def update_user_settings(
    settings: UserSettings,
    current_user: User = Depends(get_current_user)
):
    """Actualizar configuración del usuario"""
    try:
        user_service = UserService()
        success = await user_service.update_user_settings(str(current_user.id), settings)
        
        if success:
            return {"message": "Configuración actualizada correctamente"}
        else:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Endpoints de desarrollo (solo para testing)
@router.get("/all", response_model=List[UserResponse])
async def get_all_users():
    """Obtener todos los usuarios (SOLO PARA DESARROLLO)"""
    try:
        user_service = UserService()
        users = await user_service.get_all_users()
        return users
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{user_uid}", response_model=UserResponse)
async def get_user_by_uid(user_uid: str):
    """Obtener usuario específico por UID (SOLO PARA DESARROLLO)"""
    try:
        user_service = UserService()
        user = await user_service.get_user_by_uid(user_uid)
        
        if user:
            return user
        else:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
