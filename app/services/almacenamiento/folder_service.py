import logging
import re
import unicodedata
from typing import Dict, Any, Optional
from app.services.almacenamiento.s3_service import S3Service
from app.services.almacenamiento.drive_service import GoogleDriveService

logger = logging.getLogger(__name__)

class FolderService:
    """Servicio para gestionar carpetas automáticamente según categorías"""
    
    def __init__(self):
        self.s3_service = S3Service()
        # drive_service se inicializará cuando sea necesario con las credenciales del usuario
    
    async def create_category_folder(self, user_id: str, category: str, storage_preference: str) -> Dict[str, Any]:
        """Crea una carpeta para la categoría. La categoría se normaliza (primera letra mayúscula por palabra)."""
        category = self._normalize_category_name(category) or category
        try:
            # Limpiar nombre de categoría para usar como nombre de carpeta
            # Pasar storage_preference para usar el método correcto de sanitización
            folder_name = self._clean_folder_name(category, storage_preference)
            
            if storage_preference == 'keepi_cloud':
                # Crear carpeta en S3
                folder_path = f"users/{user_id}/{folder_name}/"
                result = await self._create_s3_folder(folder_path)
                
            elif storage_preference == 'google_drive':
                # Crear carpeta en Google Drive
                result = await self._create_drive_folder(folder_name, user_id)
                
            else:
                raise ValueError(f"Tipo de almacenamiento no soportado: {storage_preference}")
            
            return {
                "success": True,
                "folder_name": folder_name,
                "folder_path": result.get('path', ''),
                "folder_id": result.get('id', ''),
                "storage_type": storage_preference
            }
            
        except Exception as e:
            logger.error(f"Error creando carpeta de categoría: {e}")
            return {
                "success": False,
                "error": str(e),
                "folder_name": category,
                "storage_type": storage_preference
            }
    
    def _clean_folder_name(self, category: str, storage_preference: str = None) -> str:
        """
        Limpia el nombre de la categoría para usar como nombre de carpeta.
        Para S3 (keepi_cloud): sanitiza completamente (sin espacios ni acentos) - igual que _sanitize_folder_name
        Para Google Drive: mantiene el nombre original con espacios (solo normaliza espacios múltiples)
        """
        if storage_preference == 'keepi_cloud':
            # Para S3, usar sanitización completa (sin espacios ni caracteres especiales)
            # Primero convertir a ASCII (elimina acentos), luego sanitizar
            try:
                # Normalizar el texto (NFD descompone caracteres acentuados)
                normalized = unicodedata.normalize('NFD', category)
                # Eliminar marcas diacríticas (acentos) y convertir a ASCII
                ascii_name = normalized.encode('ascii', 'ignore').decode('ascii')
                
                # Si el texto quedó vacío, usar el nombre original
                if not ascii_name.strip():
                    ascii_name = category
                
                # Reemplazar espacios con guiones bajos y limpiar caracteres especiales
                sanitized = re.sub(r'[^a-zA-Z0-9\-_]', '_', ascii_name)
                return sanitized[:50]
            except Exception as e:
                logger.warning(f"Error sanitizando nombre de carpeta: {e}")
                # Fallback: sanitización básica
                sanitized = re.sub(r'[^a-zA-Z0-9\-_]', '_', category)
                return sanitized[:50]
        else:
            # Para Google Drive, mantener el nombre original pero normalizar espacios múltiples
            clean_name = re.sub(r'\s+', ' ', category.strip())
            # Limitar longitud
            if len(clean_name) > 100:
                clean_name = clean_name[:100]
            return clean_name
    
    async def _create_s3_folder(self, folder_path: str) -> Dict[str, Any]:
        """Crea una carpeta en S3"""
        try:
            # En S3, las carpetas se crean automáticamente al subir un archivo
            # Solo verificamos que el bucket existe
            await self.s3_service.ensure_bucket_exists()
            
            return {
                "path": folder_path,
                "id": folder_path,
                "created": True
            }
            
        except Exception as e:
            logger.error(f"Error creando carpeta en S3: {e}")
            raise
    
    async def _create_drive_folder(self, folder_name: str, user_id: str) -> Dict[str, Any]:
        """Crea una carpeta en Google Drive"""
        try:
            # Obtener credenciales del usuario usando OAuth service
            from app.services.autenticacion import GoogleOAuthService
            oauth_service = GoogleOAuthService()
            credentials = await oauth_service.refresh_user_tokens(user_id)
            
            if not credentials:
                raise Exception("Usuario no tiene credenciales de Google Drive configuradas")
            
            drive_service = GoogleDriveService(credentials)
            
            # Verificar si la carpeta ya existe
            existing_folder = await self._find_drive_folder_with_service(folder_name, drive_service)
            if existing_folder:
                return {
                    "path": existing_folder['name'],
                    "id": existing_folder['id'],
                    "created": False,
                    "already_exists": True
                }
            
            # Crear nueva carpeta
            folder_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': []  # Carpeta raíz
            }
            
            folder = drive_service.service.files().create(
                body=folder_metadata,
                fields='id, name'
            ).execute()
            
            return {
                "path": folder_name,
                "id": folder['id'],
                "created": True
            }
            
        except Exception as e:
            logger.error(f"Error creando carpeta en Drive: {e}")
            raise
    
    
    async def _find_drive_folder_with_service(self, folder_name: str, drive_service: GoogleDriveService) -> Optional[Dict[str, Any]]:
        """Busca una carpeta existente en Google Drive usando un servicio específico"""
        try:
            # Escapar comillas simples en el nombre de la carpeta para la consulta
            escaped_name = folder_name.replace("'", "\\'").replace('"', '\\"')
            query = f"name='{escaped_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
            
            logger.info("Buscando carpeta en Drive: '%s'", folder_name)
            logger.debug("Query Drive: %s", query)
            
            results = drive_service.service.files().list(
                q=query,
                fields="files(id, name)",
                spaces='drive'
            ).execute()
            
            folders = results.get('files', [])
            if folders:
                logger.info("Carpeta encontrada: '%s' (ID: %s)", folders[0]['name'], folders[0]['id'])
                return folders[0]  # Retornar la primera carpeta encontrada
            
            logger.warning("Carpeta '%s' no encontrada en Drive", folder_name)
            return None
            
        except Exception as e:
            logger.exception("Error buscando carpeta en Drive")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    def _normalize_category_name(self, category: str) -> str:
        """Normaliza el nombre de categoría: primera letra de cada palabra en mayúscula, resto en minúscula."""
        return category.strip().title() if category else ""

    async def ensure_category_folder_exists(self, user_id: str, category: str, storage_preference: str) -> Dict[str, Any]:
        """
        Asegura que existe una carpeta para la categoría, la crea si no existe.
        La categoría se normaliza (primera letra mayúscula por palabra) para no depender de mayúsculas/minúsculas.
        """
        try:
            category = self._normalize_category_name(category) or category
            if storage_preference == 'keepi_cloud':
                # Para keepi_cloud, usar sanitización completa (sin espacios ni caracteres especiales)
                folder_name = self._clean_folder_name(category, storage_preference)
                folder_path = f"users/{user_id}/{folder_name}/"
                exists = await self._check_s3_folder_exists(folder_path)
                
                return {
                    "success": True,
                    "folder_exists": exists,
                    "folder_name": folder_name,
                    "folder_id": folder_path,
                    "folder_path": folder_path,
                    "storage_type": storage_preference
                }
                
            elif storage_preference == 'google_drive':
                folder_name = self._clean_folder_name(category, storage_preference)
                # Obtener credenciales del usuario para verificar si existe la carpeta
                from app.services.autenticacion import GoogleOAuthService
                oauth_service = GoogleOAuthService()
                credentials = await oauth_service.refresh_user_tokens(user_id)
                
                if not credentials:
                    # Obtener URL de autorización usando el servicio OAuth
                    auth_data = await oauth_service.get_authorization_url(user_id)
                    return {
                        "success": False,
                        "requires_drive_auth": True,
                        "error": "Usuario no tiene credenciales de Google Drive configuradas",
                        "drive_auth_url": auth_data.get('authorization_url', ''),
                        "folder_name": category,
                        "storage_type": storage_preference
                    }
                
                try:
                    drive_service = GoogleDriveService(credentials)
                    existing_folder = await self._find_drive_folder_with_service(folder_name, drive_service)
                    
                    # Si existe, retornar inmediatamente con el folder_id
                    if existing_folder:
                        logger.info("Carpeta '%s' ya existe en Drive (ID: %s)", folder_name, existing_folder['id'])
                        return {
                            "success": True,
                            "folder_exists": True,
                            "folder_name": folder_name,
                            "folder_id": existing_folder['id'],
                            "folder_path": f"https://drive.google.com/drive/folders/{existing_folder['id']}",
                            "storage_type": storage_preference
                        }
                    
                    # Si no existe, crear la carpeta directamente usando el drive_service
                    logger.info("Carpeta '%s' no existe, creando en Drive", folder_name)
                    try:
                        folder_id = await drive_service.create_folder(folder_name)
                        logger.info("Carpeta '%s' creada (ID: %s)", folder_name, folder_id)
                        return {
                            "success": True,
                            "folder_exists": False,
                            "folder_name": folder_name,
                            "folder_id": folder_id,
                            "folder_path": f"https://drive.google.com/drive/folders/{folder_id}",
                            "storage_type": storage_preference
                        }
                    except Exception as create_error:
                        logger.error(f"Error creando carpeta en Google Drive: {create_error}")
                        raise Exception(f"No se pudo crear la carpeta en Google Drive: {str(create_error)}")
                        
                except Exception as drive_error:
                    # Si hay error con las credenciales, solicitar reautorización
                    if "invalid_grant" in str(drive_error) or "credentials" in str(drive_error).lower():
                        # Obtener URL de autorización usando el servicio OAuth
                        auth_data = await oauth_service.get_authorization_url(user_id)
                        return {
                            "success": False,
                            "requires_drive_auth": True,
                            "error": "Credenciales de Google Drive expiradas o inválidas",
                            "drive_auth_url": auth_data.get('authorization_url', ''),
                            "folder_name": category,
                            "storage_type": storage_preference
                        }
                    else:
                        raise drive_error
            else:
                raise ValueError(f"Tipo de almacenamiento no soportado: {storage_preference}")
                
        except Exception as e:
            logger.error(f"Error verificando/creando carpeta de categoría: {e}")
            return {
                "success": False,
                "error": str(e),
                "folder_name": category,
                "storage_type": storage_preference
            }
    
    async def _check_s3_folder_exists(self, folder_path: str) -> bool:
        """Verifica si una carpeta existe en S3"""
        try:
            # Listar objetos con el prefijo de la carpeta
            response = self.s3_service.s3_client.list_objects_v2(
                Bucket=self.s3_service.bucket_name,
                Prefix=folder_path,
                MaxKeys=1
            )
            
            return 'Contents' in response and len(response['Contents']) > 0
            
        except Exception as e:
            logger.error(f"Error verificando carpeta en S3: {e}")
            return False
