from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.security import HTTPBearer
from typing import List, Optional
from pydantic import BaseModel
import logging
from datetime import datetime
from app.services.almacenamiento import S3Service, GoogleDriveService
from app.services.ocr import OCRService
from app.services.aws import ComprehendService
from app.models.user import UserResponse
from app.core.security import get_current_user
from app.core.database import DatabaseConfig

router = APIRouter()
security = HTTPBearer()
logger = logging.getLogger(__name__)


async def _get_storage_preference(user_id: str) -> str:
    """Obtiene la preferencia de almacenamiento desde UserConfig."""
    from app.services.usuarios import UserConfigService
    config_service = UserConfigService()
    config = await config_service.get_or_create_user_config(user_id)
    return config.cloud_provider.value if config and config.cloud_provider else "google_drive"

# Inicializar servicios
s3_service = S3Service()
# drive_service se inicializará cuando sea necesario con las credenciales del usuario
ocr_service = OCRService()
comprehend_service = ComprehendService()

# Modelo para el request de configuración de almacenamiento
class SetupCloudStorageRequest(BaseModel):
    storage_type: str  # "keepi_cloud" | "google_drive" | "not_configured"

    class Config:
        json_schema_extra = {"example": {"storage_type": "keepi_cloud"}}


@router.post("/setup-cloud-storage")
@router.post("/configure")
async def setup_cloud_storage(
    request: SetupCloudStorageRequest,
    current_user: UserResponse = Depends(get_current_user)
):
    """
    Configura el tipo de almacenamiento: keepi_cloud (requiere pago Stripe),
    google_drive (OAuth) o not_configured (p. ej. si se cancela el pago).
    """
    try:
        logger.info(f"🔍 Recibiendo request: {request}")
        storage_type = request.storage_type
        logger.info(f"🔍 Storage type extraído: {storage_type}")

        if not storage_type or storage_type not in ["keepi_cloud", "google_drive", "not_configured"]:
            logger.error(f"❌ Tipo de almacenamiento no válido: {storage_type}")
            raise HTTPException(status_code=400, detail="Tipo de almacenamiento no válido")

        # not_configured: solo actualizar preferencia (p. ej. tras cancelar pago Stripe)
        if storage_type == "not_configured":
            try:
                from app.services.usuarios import UserConfigService
                from app.models.user_config import UserConfigUpdate, CloudProvider
                config_service = UserConfigService()
                await config_service.get_or_create_user_config(str(current_user.id))
                update_data = UserConfigUpdate(cloud_provider=CloudProvider.NOT_CONFIGURED)
                await config_service.update_user_config(str(current_user.id), update_data)
                logger.info(f"✅ cloud_provider actualizado a not_configured para usuario {current_user.id}")
                return {
                    "success": True,
                    "message": "Almacenamiento restablecido a sin configurar",
                    "storage_type": "not_configured",
                }
            except Exception as e:
                logger.error(f"Error actualizando a not_configured: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        # Validar suscripción para Keepi Cloud
        if storage_type == "keepi_cloud":
            logger.info(f"🔍 Validando suscripción para Keepi Cloud - Usuario: {current_user.id}")
            try:
                from app.services.subscription import SubscriptionService
                from app.core.database import get_db
                db = next(get_db())
                subscription_service = SubscriptionService()
                subscription = await subscription_service.get_user_subscription(str(current_user.id), db)
                
                logger.info(f"🔍 Suscripción encontrada: {subscription}")
                if subscription:
                    logger.info(f"🔍 Status de suscripción: {subscription.status.value}")
                
                if not subscription or subscription.status.value != "active" or subscription.plan.value != "premium":
                    logger.warning(f"⚠️ Suscripción no válida para Keepi Cloud - Usuario: {current_user.id}")
                    logger.info(f"🔍 Plan actual: {subscription.plan.value if subscription else 'none'}")
                    logger.info(f"🔍 Status actual: {subscription.status.value if subscription else 'none'}")
                    logger.info(f"🔍 Lanzando HTTPException 402 para usuario {current_user.id}")
                    raise HTTPException(
                        status_code=402,  # Payment Required
                        detail={
                            "error": "subscription_required",
                            "message": "Se requiere una suscripción activa para usar Keepi Cloud",
                            "subscription_info": {
                                "required_plan": "premium",
                                "current_plan": subscription.plan.value if subscription else "none",
                                "current_status": subscription.status.value if subscription else "none"
                            }
                        }
                    )
                else:
                    logger.info(f"✅ Suscripción activa para usuario {current_user.id}")
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"❌ Error validando suscripción: {e}")
                raise HTTPException(status_code=500, detail=f"Error validando suscripción: {str(e)}")
        
        # Asegurar que exista user_config, pero:
        # - Para Keepi Cloud: sí actualizamos cloud_provider inmediatamente.
        # - Para Google Drive: SOLO se actualizará a google_drive en el callback
        #   de OAuth, cuando el usuario complete la autorización.
        logger.info(f"🔄 Preparando configuración de almacenamiento para usuario {current_user.id}")
        try:
            from app.services.usuarios import UserConfigService
            from app.models.user_config import UserConfigUpdate, CloudProvider

            config_service = UserConfigService()
            user_config = await config_service.get_or_create_user_config(str(current_user.id))

            if storage_type == "keepi_cloud":
                logger.info(f"🔄 Estableciendo cloud_provider=keepi_cloud para usuario {current_user.id}")
                update_data = UserConfigUpdate(cloud_provider=CloudProvider.KEEPI_CLOUD)
                await config_service.update_user_config(str(current_user.id), update_data)
                logger.info(f"✅ cloud_provider actualizado a keepi_cloud para usuario {current_user.id}")
            # Para google_drive se actualiza más abajo solo si ya tiene credenciales;
            # si no, el callback OAuth actualizará al completar la autorización.

        except Exception as e:
            logger.error(f"❌ Error preparando/actualizando cloud_provider: {e}")
            raise HTTPException(status_code=500, detail=f"Error actualizando preferencia: {str(e)}")
        
        # Si es Keepi Cloud, crear carpeta del usuario
        if storage_type == "keepi_cloud":
            result = await s3_service.create_user_folder(str(current_user.id))
            if not result['success']:
                raise HTTPException(status_code=500, detail="Error creando carpeta de usuario")
        
        # Si es Google Drive, verificar si necesita autorización
        if storage_type == "google_drive":
            from app.services.autenticacion import GoogleOAuthService
            from app.models.user_config import UserConfigUpdate, CloudProvider

            oauth_service = GoogleOAuthService()
            credentials = await oauth_service.refresh_user_tokens(str(current_user.id))

            if not credentials:
                # Generar URL de autorización; cloud_provider se actualizará en el callback OAuth
                auth_data = await oauth_service.get_authorization_url(str(current_user.id))
                return {
                    "success": True,
                    "message": f"Almacenamiento configurado como {storage_type}",
                    "storage_type": storage_type,
                    "authorization_required": True,
                    "authorization_url": auth_data.get('authorization_url')
                }
            # Ya tiene credenciales: actualizar cloud_provider a google_drive para que la UI muestre Google Drive seleccionado
            update_data = UserConfigUpdate(cloud_provider=CloudProvider.GOOGLE_DRIVE)
            await config_service.update_user_config(str(current_user.id), update_data)
            logger.info(f"✅ cloud_provider actualizado a google_drive (ya tenía credenciales) para usuario {current_user.id}")
        return {
            "success": True,
            "message": f"Almacenamiento configurado como {storage_type}",
            "storage_type": storage_type
        }
        
    except HTTPException:
        # Re-lanzar HTTPException (incluyendo 402) sin modificar
        raise
    except Exception as e:
        logger.error(f"Error configurando almacenamiento: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/upload-document")
async def upload_document(
    file: UploadFile = File(...),
    folder: Optional[str] = Form(None),
    current_user: UserResponse = Depends(get_current_user)
):
    """
    Sube un documento al almacenamiento configurado del usuario
    """
    try:
        storage_preference = await _get_storage_preference(str(current_user.id))
        if not storage_preference:
            raise HTTPException(status_code=400, detail="Debe configurar el tipo de almacenamiento primero")

        # Leer el archivo
        file_content = await file.read()
        file_content.seek(0)  # Resetear el puntero
        
        # Procesar con OCR
        ocr_metadata = await ocr_service.extract_document_metadata(
            file_content, 
            file.filename.split('.')[-1] if '.' in file.filename else 'unknown'
        )
        
        # Categorizar con Comprehend
        categorization = await comprehend_service.categorize_document(
            ocr_metadata['extracted_text'],
            ocr_metadata['document_type']
        )
        
        # Subir según el tipo de almacenamiento
        if storage_preference == "keepi_cloud":
            upload_result = await s3_service.upload_document(
                str(current_user.id),
                file_content,
                file.filename,
                file.content_type,
                folder
            )
        else:  # google_drive
            # Implementar upload a Google Drive
            from app.services.autenticacion import GoogleOAuthService
            from app.services.almacenamiento import GoogleDriveService
            
            oauth_service = GoogleOAuthService()
            user_credentials = await oauth_service.refresh_user_tokens(str(current_user.id))
            
            if not user_credentials:
                raise HTTPException(
                    status_code=401, 
                    detail="Usuario no ha autorizado acceso a Google Drive. Use /api/v1/auth/google/authorize primero."
                )
            
            drive_service = GoogleDriveService(user_credentials)
            
            # Crear carpeta de categoría si se especifica
            if folder:
                category_folder = await drive_service.get_or_create_folder(folder)
            else:
                category_folder = await drive_service.get_or_create_folder("General")
            
            # Subir archivo a Google Drive
            drive_file_id = await drive_service.upload_file(
                file_content,
                file.filename,
                category_folder,
                file.content_type
            )
            
            upload_result = {
                'success': True,
                'file_path': f"https://drive.google.com/file/d/{drive_file_id}/view",
                'file_id': drive_file_id,
                'message': 'Documento subido a Google Drive'
            }
        
        # El documento se guarda directamente en el almacenamiento configurado
        # No necesitamos base de datos para esta funcionalidad básica
        
        return {
            "success": True,
            "document_id": "uploaded_" + str(int(datetime.now().timestamp())),
            "filename": file.filename,
            "category": categorization['category'],
            "tags": categorization['tags'],
            "extracted_text": ocr_metadata['extracted_text'][:500],  # Primeros 500 caracteres
            "storage_type": storage_preference,
            "upload_result": upload_result
        }

    except Exception as e:
        logger.error(f"Error subiendo documento: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/documents")
async def get_documents(
    folder: Optional[str] = None,
    category: Optional[str] = None,
    current_user: UserResponse = Depends(get_current_user)
):
    """
    Obtiene la lista de documentos del usuario
    """
    try:
        # Para simplificar, retornamos una lista vacía
        # En una implementación completa, se consultaría Firestore
        return {
            "success": True,
            "documents": [],
            "message": "Funcionalidad de listado de documentos no implementada completamente"
        }
        
    except Exception as e:
        logger.error(f"Error obteniendo documentos: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/folders")
async def get_folders(
    current_user: UserResponse = Depends(get_current_user)
):
    """
    Obtiene la lista de carpetas del usuario
    """
    try:
        storage_preference = await _get_storage_preference(str(current_user.id))
        if not storage_preference:
            raise HTTPException(status_code=400, detail="Debe configurar el tipo de almacenamiento primero")

        if storage_preference == "keepi_cloud":
            result = await s3_service.list_user_documents(str(current_user.id))
        else:  # google_drive
            # TODO: Implementar listado de carpetas de Google Drive
            result = {'folders': []}

        return {
            "success": True,
            "folders": result.get('folders', []),
            "storage_type": storage_preference
        }
        
    except Exception as e:
        logger.error(f"Error obteniendo carpetas: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/create-folder")
async def create_folder(
    folder_name: str = Form(...),
    parent_folder: Optional[str] = Form(None),
    current_user: UserResponse = Depends(get_current_user)
):
    """
    Crea una nueva carpeta
    """
    try:
        storage_preference = await _get_storage_preference(str(current_user.id))
        if not storage_preference:
            raise HTTPException(status_code=400, detail="Debe configurar el tipo de almacenamiento primero")

        if storage_preference == "keepi_cloud":
            result = await s3_service.create_folder(
                str(current_user.id),
                folder_name,
                parent_folder
            )
        else:  # google_drive
            # Implementar creación de carpeta en Google Drive
            from app.services.autenticacion import GoogleOAuthService
            from app.services.almacenamiento import GoogleDriveService
            
            oauth_service = GoogleOAuthService()
            user_credentials = await oauth_service.refresh_user_tokens(str(current_user.id))
            
            if not user_credentials:
                raise HTTPException(
                    status_code=401, 
                    detail="Usuario no ha autorizado acceso a Google Drive. Use /api/v1/auth/google/authorize primero."
                )
            
            drive_service = GoogleDriveService(user_credentials)
            
            # Crear carpeta en Google Drive
            folder_id = await drive_service.create_folder(folder_name, parent_folder)
            
            result = {
                'success': True,
                'folder_path': f"https://drive.google.com/drive/folders/{folder_id}",
                'folder_id': folder_id,
                'message': 'Carpeta creada en Google Drive'
            }
        
        return result
        
    except Exception as e:
        logger.error(f"Error creando carpeta: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/download-document/{document_id}")
async def download_document(
    document_id: str,
    current_user: UserResponse = Depends(get_current_user)
):
    """
    Descarga un documento
    """
    try:
        # Para simplificar, retornamos un error
        # En una implementación completa, se consultaría Firestore
        raise HTTPException(status_code=501, detail="Funcionalidad de descarga no implementada completamente")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error descargando documento: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/delete-document/{document_id}")
async def delete_document(
    document_id: str,
    current_user: UserResponse = Depends(get_current_user)
):
    """
    Elimina un documento
    """
    try:
        # Para simplificar, retornamos un error
        # En una implementación completa, se consultaría Firestore
        raise HTTPException(status_code=501, detail="Funcionalidad de eliminación no implementada completamente")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error eliminando documento: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/storage-usage")
async def get_storage_usage(
    current_user: UserResponse = Depends(get_current_user)
):
    """
    Obtiene el uso de almacenamiento del usuario
    """
    try:
        storage_preference = await _get_storage_preference(str(current_user.id))
        if not storage_preference:
            raise HTTPException(status_code=400, detail="Debe configurar el tipo de almacenamiento primero")

        if storage_preference == "keepi_cloud":
            result = await s3_service.get_storage_usage(str(current_user.id))
        else:  # google_drive
            # Implementar uso de almacenamiento de Google Drive
            from app.services.autenticacion import GoogleOAuthService
            from app.services.almacenamiento import GoogleDriveService
            
            oauth_service = GoogleOAuthService()
            user_credentials = await oauth_service.refresh_user_tokens(str(current_user.id))
            
            if not user_credentials:
                raise HTTPException(
                    status_code=401, 
                    detail="Usuario no ha autorizado acceso a Google Drive. Use /api/v1/auth/google/authorize primero."
                )
            
            drive_service = GoogleDriveService(user_credentials)
            
            # Obtener todos los archivos del usuario
            all_files = await drive_service.get_all_files()
            
            # Calcular uso total
            total_size = 0
            for file_info in all_files:
                try:
                    file_size = int(file_info.get('size', '0'))
                    total_size += file_size
                except (ValueError, TypeError):
                    continue
            
            total_size_mb = total_size / (1024 * 1024)
            file_count = len(all_files)
            storage_limit_mb = 15000  # 15GB gratis de Google Drive
            usage_percentage = (total_size_mb / storage_limit_mb) * 100
            
            result = {
                'total_size_mb': round(total_size_mb, 2),
                'file_count': file_count,
                'storage_limit_mb': storage_limit_mb,
                'usage_percentage': round(usage_percentage, 2)
            }
        
        return result
        
    except Exception as e:
        logger.error(f"Error obteniendo uso de almacenamiento: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/cloud-providers")
async def get_cloud_providers():
    """
    Obtiene la lista de proveedores de almacenamiento disponibles
    """
    try:
        providers = [
            {
                "provider": "keepi_cloud",
                "name": "KIPI Cloud",
                "description": "Almacenamiento seguro en la nube de KIPI",
                "features": [
                    "Almacenamiento ilimitado",
                    "Cifrado de extremo a extremo",
                    "Sincronización automática",
                    "Respaldo automático"
                ],
                "storage_limit": "Ilimitado",
                "is_available": True
            },
            {
                "provider": "google_drive",
                "name": "Google Drive",
                "description": "Integración con tu Google Drive existente",
                "features": [
                    "15GB de almacenamiento gratis",
                    "Integración con Google Workspace",
                    "Colaboración en tiempo real",
                    "Acceso desde cualquier dispositivo"
                ],
                "storage_limit": "15GB gratis",
                "is_available": True
            }
        ]
        
        return {
            "success": True,
            "data": providers
        }
        
    except Exception as e:
        logger.error(f"Error obteniendo proveedores: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/storage-status")
async def get_storage_status(
    current_user: UserResponse = Depends(get_current_user)
):
    """
    Obtiene el estado actual del almacenamiento configurado
    """
    try:
        storage_preference = await _get_storage_preference(str(current_user.id))
        if not storage_preference:
            return {
                "configured": False,
                "storage_type": None,
                "message": "No hay tipo de almacenamiento configurado"
            }

        # Verificar estado según el tipo de almacenamiento
        if storage_preference == "keepi_cloud":
            try:
                # Verificar acceso a S3
                await s3_service.get_storage_usage(str(current_user.id))
                return {
                    "configured": True,
                    "storage_type": "keepi_cloud",
                    "status": "active",
                    "message": "KIPI Cloud configurado y funcionando"
                }
            except Exception as e:
                return {
                    "configured": True,
                    "storage_type": "keepi_cloud",
                    "status": "error",
                    "message": f"Error en KIPI Cloud: {str(e)}"
                }
        else:  # google_drive
            try:
                # Verificar acceso a Google Drive
                from app.services.autenticacion import GoogleOAuthService
                from app.services.almacenamiento import GoogleDriveService
                
                oauth_service = GoogleOAuthService()
                user_credentials = await oauth_service.refresh_user_tokens(str(current_user.id))
                
                if not user_credentials:
                    return {
                        "configured": True,
                        "storage_type": "google_drive",
                        "status": "auth_required",
                        "message": "Google Drive configurado pero requiere autorización"
                    }
                
                # Probar acceso a Google Drive
                drive_service = GoogleDriveService(user_credentials)
                await drive_service.get_folder_structure()
                
                return {
                    "configured": True,
                    "storage_type": "google_drive",
                    "status": "active",
                    "message": "Google Drive configurado y funcionando"
                }
            except Exception as e:
                return {
                    "configured": True,
                    "storage_type": "google_drive",
                    "status": "error",
                    "message": f"Error en Google Drive: {str(e)}"
                }
        
    except Exception as e:
        logger.error(f"Error verificando estado de almacenamiento: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/drive-auth-status")
async def get_drive_auth_status(
    current_user: UserResponse = Depends(get_current_user)
):
    """
    Verifica el estado de autorización de Google Drive del usuario
    """
    try:
        from app.services.autenticacion import GoogleOAuthService

        storage_preference = await _get_storage_preference(str(current_user.id))
        oauth_service = GoogleOAuthService()
        auth_status = await oauth_service.check_user_drive_access(str(current_user.id))

        return {
            "user_id": str(current_user.id),
            "storage_preference": storage_preference,
            "drive_auth_status": auth_status,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error verificando estado de autorización de Drive: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
