from fastapi import APIRouter, Depends, HTTPException, status
from typing import List

from app.utils.auth import verify_token
from app.services.user_service import UserService
from app.models.user import UserCreate, UserUpdate, UserResponse, UserSettings

router = APIRouter()

@router.get("/profile", response_model=UserResponse)
async def get_user_profile(user_token: dict = Depends(verify_token)):
    """Obtener perfil del usuario autenticado"""
    try:
        user_service = UserService()
        user = await user_service.get_user_by_uid(user_token['uid'])
        
        if user:
            return user
        else:
            # Crear nuevo perfil de usuario
            new_user_data = UserCreate(
                uid=user_token['uid'],
                email=user_token.get('email', ''),
                name=user_token.get('name', '')
            )
            return await user_service.create_user(new_user_data)
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/profile", response_model=UserResponse)
async def update_user_profile(
    user_data: UserUpdate,
    user_token: dict = Depends(verify_token)
):
    """Actualizar perfil del usuario"""
    try:
        user_service = UserService()
        updated_user = await user_service.update_user(user_token['uid'], user_data)
        
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
    user_token: dict = Depends(verify_token)
):
    """Actualizar configuración del usuario"""
    try:
        user_service = UserService()
        success = await user_service.update_user_settings(user_token['uid'], settings)
        
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
