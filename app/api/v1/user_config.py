from fastapi import APIRouter, Depends, HTTPException, status
from typing import List

from app.utils.auth import verify_token
from app.services.user_config_service import UserConfigService
from app.models.user_config import (
    UserConfigCreate, 
    UserConfigUpdate, 
    UserConfigResponse, 
    CloudProvider,
    CloudProviderInfo
)

router = APIRouter()

@router.get("/", response_model=UserConfigResponse)
async def get_user_config(user_token: dict = Depends(verify_token)):
    """Obtener configuración del usuario"""
    try:
        config_service = UserConfigService()
        config = await config_service.get_or_create_user_config(user_token['uid'])
        return config
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/", response_model=UserConfigResponse)
async def create_user_config(
    config_data: UserConfigCreate,
    user_token: dict = Depends(verify_token)
):
    """Crear configuración de usuario"""
    try:
        config_service = UserConfigService()
        config = await config_service.create_user_config(user_token['uid'], config_data)
        return config
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/", response_model=UserConfigResponse)
async def update_user_config(
    config_data: UserConfigUpdate,
    user_token: dict = Depends(verify_token)
):
    """Actualizar configuración de usuario"""
    try:
        config_service = UserConfigService()
        config = await config_service.update_user_config(user_token['uid'], config_data)
        
        if not config:
            raise HTTPException(status_code=404, detail="Configuración de usuario no encontrada")
        
        return config
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/cloud-providers", response_model=List[CloudProviderInfo])
async def get_available_cloud_providers(user_token: dict = Depends(verify_token)):
    """Obtener proveedores de nube disponibles"""
    try:
        config_service = UserConfigService()
        providers = await config_service.get_available_cloud_providers()
        return providers
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/switch-cloud-provider", response_model=UserConfigResponse)
async def switch_cloud_provider(
    new_provider: CloudProvider,
    user_token: dict = Depends(verify_token)
):
    """Cambiar proveedor de nube del usuario"""
    try:
        config_service = UserConfigService()
        config = await config_service.switch_cloud_provider(user_token['uid'], new_provider)
        return config
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/first-time-setup")
async def get_first_time_setup_info(user_token: dict = Depends(verify_token)):
    """Obtener información para configuración inicial del usuario"""
    try:
        config_service = UserConfigService()
        
        # Verificar si es la primera vez que el usuario usa Keepi
        config = await config_service.get_user_config(user_token['uid'])
        is_first_time = config is None
        
        # Obtener proveedores disponibles
        providers = await config_service.get_available_cloud_providers()
        
        return {
            "is_first_time": is_first_time,
            "cloud_providers": providers,
            "message": "¿Usar Keepi Cloud (S3) o Google Drive?" if is_first_time else "Configuración actual"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
