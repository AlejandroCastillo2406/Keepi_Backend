from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.security import HTTPBearer
from typing import List, Optional
import logging
from datetime import datetime
from app.services.s3_service import S3Service
from app.services.drive_service import GoogleDriveService
from app.services.ocr_service import OCRService
from app.services.comprehend_service import ComprehendService
from app.models.user import UserResponse
from app.api.v1.auth import get_current_user
from app.config.database import DatabaseConfig

router = APIRouter()
security = HTTPBearer()
logger = logging.getLogger(__name__)

# Inicializar servicios
s3_service = S3Service()
# drive_service se inicializará cuando sea necesario con las credenciales del usuario
ocr_service = OCRService()
comprehend_service = ComprehendService()

@router.post("/setup-cloud-storage")
async def setup_cloud_storage(
    storage_type: str = Form(...),  # "keepi_cloud" o "google_drive"
    current_user: UserResponse = Depends(get_current_user)
):
    """
    Configura el tipo de almacenamiento en la nube para el usuario
    """
    try:
        if storage_type not in ["keepi_cloud", "google_drive"]:
            raise HTTPException(status_code=400, detail="Tipo de almacenamiento no válido")
        
        # Actualizar preferencia del usuario en PostgreSQL
        from app.services.user_service import UserService
        user_service = UserService()
        logger.info(f"Actualizando storage_preference para usuario {current_user.id} a {storage_type}")
        
        success = await user_service.update_user_fields(
            str(current_user.id), 
            {"storage_preference": storage_type}
        )
        
        if not success:
            logger.error(f"Error actualizando storage_preference para usuario {current_user.id}")
            raise HTTPException(status_code=500, detail="Error actualizando preferencia de almacenamiento")
        
        # Si es Keepi Cloud, crear carpeta del usuario
        if storage_type == "keepi_cloud":
            result = await s3_service.create_user_folder(str(current_user.id))
            if not result['success']:
                raise HTTPException(status_code=500, detail="Error creando carpeta de usuario")
        
        # Si es Google Drive, verificar si necesita autorización
        if storage_type == "google_drive":
            from app.services.oauth_service import GoogleOAuthService
            oauth_service = GoogleOAuthService()
            credentials = await oauth_service.refresh_user_tokens(str(current_user.id))
            
            if not credentials:
                # Generar URL de autorización
                auth_data = await oauth_service.get_authorization_url(str(current_user.id))
                return {
                    "success": True,
                    "message": f"Almacenamiento configurado como {storage_type}",
                    "storage_type": storage_type,
                    "authorization_required": True,
                    "authorization_url": auth_data.get('authorization_url')
                }
        
        return {
            "success": True,
            "message": f"Almacenamiento configurado como {storage_type}",
            "storage_type": storage_type
        }
        
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
        # Verificar que el usuario tenga configurado el almacenamiento
        if not current_user.storage_preference:
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
        if current_user.storage_preference == "keepi_cloud":
            upload_result = await s3_service.upload_document(
                str(current_user.id),
                file_content,
                file.filename,
                file.content_type,
                folder
            )
        else:  # google_drive
            # Implementar upload a Google Drive
            from app.services.oauth_service import GoogleOAuthService
            from app.services.drive_service import GoogleDriveService
            
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
            "storage_type": current_user.storage_preference,
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
        if not current_user.storage_preference:
            raise HTTPException(status_code=400, detail="Debe configurar el tipo de almacenamiento primero")
        
        if current_user.storage_preference == "keepi_cloud":
            result = await s3_service.list_user_documents(str(current_user.id))
        else:  # google_drive
            # TODO: Implementar listado de carpetas de Google Drive
            result = {'folders': []}
        
        return {
            "success": True,
            "folders": result.get('folders', []),
            "storage_type": current_user.storage_preference
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
        if not current_user.storage_preference:
            raise HTTPException(status_code=400, detail="Debe configurar el tipo de almacenamiento primero")
        
        if current_user.storage_preference == "keepi_cloud":
            result = await s3_service.create_folder(
                str(current_user.id),
                folder_name,
                parent_folder
            )
        else:  # google_drive
            # Implementar creación de carpeta en Google Drive
            from app.services.oauth_service import GoogleOAuthService
            from app.services.drive_service import GoogleDriveService
            
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
        if not current_user.storage_preference:
            raise HTTPException(status_code=400, detail="Debe configurar el tipo de almacenamiento primero")
        
        if current_user.storage_preference == "keepi_cloud":
            result = await s3_service.get_storage_usage(str(current_user.id))
        else:  # google_drive
            # Implementar uso de almacenamiento de Google Drive
            from app.services.oauth_service import GoogleOAuthService
            from app.services.drive_service import GoogleDriveService
            
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

@router.post("/change-storage-type")
async def change_storage_type(
    new_storage_type: str = Form(...),
    current_user: UserResponse = Depends(get_current_user)
):
    """
    Cambia el tipo de almacenamiento del usuario
    """
    try:
        if new_storage_type not in ["keepi_cloud", "google_drive"]:
            raise HTTPException(status_code=400, detail="Tipo de almacenamiento no válido")
        
        # Actualizar preferencia del usuario en Firestore
        from app.services.user_service import UserService
        user_service = UserService()
        await user_service.update_user_fields(
            str(current_user.id), 
            {"storage_preference": new_storage_type}
        )
        
        # Si es Keepi Cloud, crear carpeta del usuario si no existe
        if new_storage_type == "keepi_cloud":
            try:
                await s3_service.create_user_folder(str(current_user.id))
            except:
                pass  # La carpeta ya existe
        
        return {
            "success": True,
            "message": f"Tipo de almacenamiento cambiado a {new_storage_type}",
            "storage_type": new_storage_type
        }
        
    except Exception as e:
        logger.error(f"Error cambiando tipo de almacenamiento: {str(e)}")
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

@router.get("/first-time-setup")
async def get_first_time_setup(
    current_user: UserResponse = Depends(get_current_user)
):
    """
    Verifica si es la primera vez que el usuario configura el almacenamiento
    """
    try:
        is_first_time = not current_user.storage_preference
        
        return {
            "success": True,
            "data": {
                "is_first_time": is_first_time,
                "storage_configured": bool(current_user.storage_preference),
                "storage_type": current_user.storage_preference
            }
        }
        
    except Exception as e:
        logger.error(f"Error verificando configuración inicial: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/storage-status")
async def get_storage_status(
    current_user: UserResponse = Depends(get_current_user)
):
    """
    Obtiene el estado actual del almacenamiento configurado
    """
    try:
        if not current_user.storage_preference:
            return {
                "configured": False,
                "storage_type": None,
                "message": "No hay tipo de almacenamiento configurado"
            }
        
        # Verificar estado según el tipo de almacenamiento
        if current_user.storage_preference == "keepi_cloud":
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
                from app.services.oauth_service import GoogleOAuthService
                from app.services.drive_service import GoogleDriveService
                
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
        from app.services.oauth_service import GoogleOAuthService
        
        oauth_service = GoogleOAuthService()
        auth_status = await oauth_service.check_user_drive_access(str(current_user.id))
        
        return {
            "user_id": str(current_user.id),
            "storage_preference": current_user.storage_preference,
            "drive_auth_status": auth_status,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error verificando estado de autorización de Drive: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
