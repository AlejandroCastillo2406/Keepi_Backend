from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import List

from app.core.security import get_current_user
from app.services.usuarios import UserService
from app.models.user import UserCreate, UserUpdate, UserResponse, User

router = APIRouter()

# IMPORTANTE: Las rutas específicas deben ir ANTES que las rutas dinámicas

@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """Obtener información del usuario autenticado (endpoint /me)"""
    return UserResponse.from_orm(current_user)

@router.get("/debug-token")
async def debug_token(credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer(auto_error=False))):
    """Debug del token JWT"""
    if credentials is None:
        return {"error": "No se proporcionó token"}
    
    try:
        from jose import jwt
        from app.core.config import settings
        
        token = credentials.credentials
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm], options={"verify_exp": False})
        
        return {
            "token_payload": payload,
            "user_id_from_token": payload.get("sub"),
            "email_from_token": payload.get("email")
        }
    except Exception as e:
        return {"error": f"Error decodificando token: {str(e)}"}

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

# Endpoints de desarrollo (solo para testing) - ANTES de rutas dinámicas
@router.get("/all", response_model=List[UserResponse])
async def get_all_users():
    """Obtener todos los usuarios (SOLO PARA DESARROLLO)"""
    try:
        user_service = UserService()
        users = await user_service.get_all_users()
        return users
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# RUTA DINÁMICA - DEBE IR AL FINAL
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
