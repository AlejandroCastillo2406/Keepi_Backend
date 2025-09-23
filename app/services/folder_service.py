import logging
from typing import Dict, Any, Optional
from app.services.s3_service import S3Service
from app.services.drive_service import GoogleDriveService

logger = logging.getLogger(__name__)

class FolderService:
    """Servicio para gestionar carpetas automáticamente según categorías"""
    
    def __init__(self):
        self.s3_service = S3Service()
        # drive_service se inicializará cuando sea necesario con las credenciales del usuario
    
    async def create_category_folder(self, user_id: str, category: str, storage_preference: str) -> Dict[str, Any]:
        """
        Crea una carpeta para la categoría en el almacenamiento configurado
        """
        try:
            # Limpiar nombre de categoría para usar como nombre de carpeta
            folder_name = self._clean_folder_name(category)
            
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
    
    def _clean_folder_name(self, category: str) -> str:
        """Limpia el nombre de la categoría para usar como nombre de carpeta"""
        # Reemplazar caracteres especiales y espacios
        import re
        clean_name = re.sub(r'[^\w\s-]', '', category)
        clean_name = re.sub(r'[-\s]+', '_', clean_name)
        clean_name = clean_name.strip('_')
        
        # Limitar longitud
        if len(clean_name) > 50:
            clean_name = clean_name[:50]
        
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
            from app.services.oauth_service import GoogleOAuthService
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
            query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
            results = drive_service.service.files().list(
                q=query,
                fields="files(id, name)"
            ).execute()
            
            folders = results.get('files', [])
            if folders:
                return folders[0]  # Retornar la primera carpeta encontrada
            
            return None
            
        except Exception as e:
            logger.error(f"Error buscando carpeta en Drive con servicio específico: {e}")
            return None
    
    async def ensure_category_folder_exists(self, user_id: str, category: str, storage_preference: str) -> Dict[str, Any]:
        """
        Asegura que existe una carpeta para la categoría, la crea si no existe
        """
        try:
            # Verificar si la carpeta ya existe
            if storage_preference == 'keepi_cloud':
                folder_path = f"users/{user_id}/{self._clean_folder_name(category)}/"
                exists = await self._check_s3_folder_exists(folder_path)
                
            elif storage_preference == 'google_drive':
                folder_name = self._clean_folder_name(category)
                # Obtener credenciales del usuario para verificar si existe la carpeta
                from app.services.oauth_service import GoogleOAuthService
                oauth_service = GoogleOAuthService()
                credentials = await oauth_service.refresh_user_tokens(user_id)
                
                if not credentials:
                    from app.config.settings import GOOGLE_CLIENT_ID, GOOGLE_REDIRECT_URI
                    drive_auth_url = (
                        f"https://accounts.google.com/o/oauth2/auth?client_id={GOOGLE_CLIENT_ID}"
                        f"&redirect_uri={GOOGLE_REDIRECT_URI}"
                        "&scope=https://www.googleapis.com/auth/drive"
                        "&response_type=code&access_type=offline&prompt=consent"
                    )
                    return {
                        "success": False,
                        "requires_drive_auth": True,
                        "error": "Usuario no tiene credenciales de Google Drive configuradas",
                        "drive_auth_url": drive_auth_url,
                        "folder_name": category,
                        "storage_type": storage_preference
                    }
                
                try:
                    drive_service = GoogleDriveService(credentials)
                    exists = await self._find_drive_folder_with_service(folder_name, drive_service) is not None
                except Exception as drive_error:
                    # Si hay error con las credenciales, solicitar reautorización
                    if "invalid_grant" in str(drive_error) or "credentials" in str(drive_error).lower():
                        from app.config.settings import GOOGLE_CLIENT_ID, GOOGLE_REDIRECT_URI
                        drive_auth_url = (
                            f"https://accounts.google.com/o/oauth2/auth?client_id={GOOGLE_CLIENT_ID}"
                            f"&redirect_uri={GOOGLE_REDIRECT_URI}"
                            "&scope=https://www.googleapis.com/auth/drive"
                            "&response_type=code&access_type=offline&prompt=consent"
                        )
                        return {
                            "success": False,
                            "requires_drive_auth": True,
                            "error": "Credenciales de Google Drive expiradas o inválidas",
                            "drive_auth_url": drive_auth_url,
                            "folder_name": category,
                            "storage_type": storage_preference
                        }
                    else:
                        raise drive_error
                
            else:
                raise ValueError(f"Tipo de almacenamiento no soportado: {storage_preference}")
            
            if exists:
                return {
                    "success": True,
                    "folder_exists": True,
                    "folder_name": self._clean_folder_name(category),
                    "storage_type": storage_preference
                }
            else:
                # Crear la carpeta
                return await self.create_category_folder(user_id, category, storage_preference)
                
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
