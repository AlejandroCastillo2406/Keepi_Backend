import boto3
import json
import logging
import unicodedata
import re
from typing import Dict, List, Optional, Any, BinaryIO
from botocore.exceptions import ClientError
import uuid
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class S3Service:
    def __init__(self):
        self.s3_client = boto3.client('s3')
        self.bucket_name = 'keepi-bucket'  # Bucket principal de Keepi
        
    async def ensure_bucket_exists(self) -> bool:
        """
        Verifica si el bucket existe y lo crea si no existe
        """
        try:
            # Verificar si el bucket existe
            try:
                self.s3_client.head_bucket(Bucket=self.bucket_name)
                logger.info(f"Bucket '{self.bucket_name}' ya existe")
                return True
            except ClientError as e:
                error_code = e.response['Error']['Code']
                if error_code == '404':
                    logger.info(f"Bucket '{self.bucket_name}' no existe, creándolo...")
                elif error_code == '403':
                    logger.error(f"No tienes permisos para acceder al bucket '{self.bucket_name}'")
                    raise
                else:
                    logger.error(f"Error verificando bucket: {e}")
                    raise
            
            # Crear el bucket si no existe
            region = 'us-east-1'
            if region == 'us-east-1':
                # us-east-1 no necesita LocationConstraint
                self.s3_client.create_bucket(Bucket=self.bucket_name)
            else:
                # Otras regiones necesitan LocationConstraint
                self.s3_client.create_bucket(
                    Bucket=self.bucket_name,
                    CreateBucketConfiguration={'LocationConstraint': region}
                )
            
            logger.info(f"Bucket '{self.bucket_name}' creado exitosamente")
            
            # Configurar CORS
            cors_configuration = {
                'CORSRules': [
                    {
                        'AllowedHeaders': ['*'],
                        'AllowedMethods': ['GET', 'PUT', 'POST', 'DELETE'],
                        'AllowedOrigins': ['*'],
                        'ExposeHeaders': ['ETag'],
                        'MaxAgeSeconds': 3000
                    }
                ]
            }
            
            self.s3_client.put_bucket_cors(Bucket=self.bucket_name, CORSConfiguration=cors_configuration)
            logger.info(f"Configuración CORS aplicada al bucket '{self.bucket_name}'")
            
            return True
            
        except Exception as e:
            logger.error(f"Error asegurando que el bucket existe: {str(e)}")
            raise
        
    async def create_user_folder(self, user_id: str) -> Dict[str, Any]:
        """
        Crea una carpeta para el usuario en S3
        """
        try:
            folder_path = f"users/{user_id}/"
            
            # Crear la carpeta (en S3 se crea como un objeto con '/' al final)
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=folder_path,
                Body=b'',
                Metadata={
                    'user_id': user_id,
                    'created_at': datetime.utcnow().isoformat(),
                    'type': 'folder'
                }
            )
            
            return {
                'success': True,
                'folder_path': folder_path,
                'message': 'Carpeta de usuario creada exitosamente'
            }
            
        except Exception as e:
            logger.error(f"Error creando carpeta de usuario: {str(e)}")
            raise
    
    async def upload_document(self, user_id: str, file_data: BinaryIO, filename: str, 
                            content_type: str, folder: str = None) -> Dict[str, Any]:
        """
        Sube un documento a S3
        """
        try:
            # Generar nombre único para el archivo
            file_extension = filename.split('.')[-1] if '.' in filename else ''
            unique_filename = f"{uuid.uuid4()}.{file_extension}"
            
            # Determinar la carpeta de destino
            if not folder:
                # Si no se especifica carpeta, usar 'other' como fallback
                folder = 'other'
            
            # Asegurar que la carpeta termine con '/'
            if not folder.endswith('/'):
                folder += '/'
            
            # Crear la carpeta de categoría si no existe
            await self._ensure_category_folder_exists(user_id, folder)
            
            # Ruta completa del archivo
            file_path = f"users/{user_id}/{folder}{unique_filename}"
            
            # Leer el contenido del archivo para evitar problemas de I/O
            file_content = file_data.read()
            file_size = len(file_content)
            
            # Convertir campos a ASCII seguro para metadatos de S3
            original_filename_ascii = self._to_ascii_safe(filename)
            folder_ascii = self._to_ascii_safe(folder.rstrip('/')) if folder else 'other'
            
            # Subir el archivo usando put_object en lugar de upload_fileobj
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=file_path,
                Body=file_content,
                ContentType=content_type,
                Metadata={
                    'user_id': user_id,
                    'original_filename': original_filename_ascii,
                    'uploaded_at': datetime.utcnow().isoformat(),
                    'folder': folder_ascii
                }
            )
            
            # Generar URL firmada para acceso temporal
            signed_url = self._generate_signed_url(file_path, expiration=3600)  # 1 hora
            
            return {
                'success': True,
                'file_path': file_path,
                'filename': unique_filename,
                'original_filename': filename,
                'signed_url': signed_url,
                'folder': folder,
                'size': file_size
            }
            
        except Exception as e:
            logger.error(f"Error subiendo documento: {str(e)}")
            raise
    
    async def download_document(self, user_id: str, file_path: str) -> Dict[str, Any]:
        """
        Descarga un documento de S3
        """
        try:
            # Verificar que el archivo pertenece al usuario
            if not file_path.startswith(f"users/{user_id}/"):
                raise ValueError("No tienes permisos para acceder a este archivo")
            
            # Generar URL firmada para descarga
            signed_url = self._generate_signed_url(file_path, expiration=3600)
            
            # Obtener metadatos del archivo
            response = self.s3_client.head_object(
                Bucket=self.bucket_name,
                Key=file_path
            )
            
            return {
                'success': True,
                'signed_url': signed_url,
                'filename': response['Metadata'].get('original_filename', file_path.split('/')[-1]),
                'content_type': response['ContentType'],
                'size': response['ContentLength'],
                'last_modified': response['LastModified'].isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error descargando documento: {str(e)}")
            raise
    
    async def delete_document(self, user_id: str, file_path: str) -> Dict[str, Any]:
        """
        Elimina un documento de S3
        """
        try:
            # Verificar que el archivo pertenece al usuario
            if not file_path.startswith(f"users/{user_id}/"):
                raise ValueError("No tienes permisos para eliminar este archivo")
            
            # Eliminar el archivo
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=file_path
            )
            
            return {
                'success': True,
                'message': 'Documento eliminado exitosamente'
            }
            
        except Exception as e:
            logger.error(f"Error eliminando documento: {str(e)}")
            raise
    
    async def list_user_documents(self, user_id: str, folder: str = None) -> List[Dict[str, Any]]:
        """
        Lista todos los documentos del usuario
        """
        try:
            prefix = f"users/{user_id}/"
            if folder:
                prefix += f"{folder}/"
            
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix,
                Delimiter='/'
            )
            
            documents = []
            
            # Procesar archivos
            for obj in response.get('Contents', []):
                if obj['Key'].endswith('/'):  # Saltar carpetas
                    continue
                
                # Obtener metadatos
                metadata_response = self.s3_client.head_object(
                    Bucket=self.bucket_name,
                    Key=obj['Key']
                )
                
                documents.append({
                    'file_path': obj['Key'],
                    'filename': metadata_response['Metadata'].get('original_filename', obj['Key'].split('/')[-1]),
                    'size': obj['Size'],
                    'last_modified': obj['LastModified'].isoformat(),
                    'content_type': metadata_response['ContentType'],
                    'folder': metadata_response['Metadata'].get('folder', 'other')
                })
            
            # Procesar carpetas
            folders = []
            for prefix_obj in response.get('CommonPrefixes', []):
                folder_name = prefix_obj['Prefix'].split('/')[-2]  # Obtener nombre de la carpeta
                folders.append({
                    'name': folder_name,
                    'path': prefix_obj['Prefix']
                })
            
            return {
                'documents': documents,
                'folders': folders
            }
            
        except Exception as e:
            logger.error(f"Error listando documentos: {str(e)}")
            raise
    
    async def create_folder(self, user_id: str, folder_name: str, parent_folder: str = None) -> Dict[str, Any]:
        """
        Crea una nueva carpeta en S3
        """
        try:
            # Sanitizar nombre de carpeta para S3 (sin espacios ni caracteres especiales)
            sanitized_folder_name = self._sanitize_folder_name(folder_name)
            # Convertir a ASCII para metadatos
            folder_name_ascii = self._to_ascii_safe(folder_name)
            
            if parent_folder:
                # También sanitizar parent_folder
                sanitized_parent = self._sanitize_folder_name(parent_folder)
                folder_path = f"users/{user_id}/{sanitized_parent}/{sanitized_folder_name}/"
            else:
                folder_path = f"users/{user_id}/{sanitized_folder_name}/"
            
            # Crear la carpeta
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=folder_path,
                Body=b'',
                Metadata={
                    'user_id': user_id,
                    'created_at': datetime.utcnow().isoformat(),
                    'type': 'folder',
                    'parent_folder': self._to_ascii_safe(parent_folder) if parent_folder else 'root',
                    'folder_name': folder_name_ascii  # Nombre original en ASCII
                }
            )
            
            return {
                'success': True,
                'folder_path': folder_path,
                'folder_name': sanitized_folder_name,
                'message': 'Carpeta creada exitosamente'
            }
            
        except Exception as e:
            logger.error(f"Error creando carpeta: {str(e)}")
            raise
    
    async def move_document(self, user_id: str, file_path: str, new_folder: str) -> Dict[str, Any]:
        """
        Mueve un documento a otra carpeta
        """
        try:
            # Verificar que el archivo pertenece al usuario
            if not file_path.startswith(f"users/{user_id}/"):
                raise ValueError("No tienes permisos para mover este archivo")
            
            # Obtener el nombre del archivo
            filename = file_path.split('/')[-1]
            new_file_path = f"users/{user_id}/{new_folder}/{filename}"
            
            # Copiar el archivo a la nueva ubicación
            copy_source = {
                'Bucket': self.bucket_name,
                'Key': file_path
            }
            
            self.s3_client.copy_object(
                CopySource=copy_source,
                Bucket=self.bucket_name,
                Key=new_file_path
            )
            
            # Eliminar el archivo original
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=file_path
            )
            
            return {
                'success': True,
                'new_file_path': new_file_path,
                'message': 'Documento movido exitosamente'
            }
            
        except Exception as e:
            logger.error(f"Error moviendo documento: {str(e)}")
            raise
    
    def _generate_signed_url(self, file_path: str, expiration: int = 3600) -> str:
        """
        Genera una URL firmada para acceso temporal al archivo
        """
        try:
            signed_url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket_name, 'Key': file_path},
                ExpiresIn=expiration
            )
            return signed_url
            
        except Exception as e:
            logger.error(f"Error generando URL firmada: {str(e)}")
            raise
    
    async def _ensure_category_folder_exists(self, user_id: str, folder_name: str) -> None:
        """
        Asegura que la carpeta de categoría existe para el usuario
        """
        try:
            folder_path = f"users/{user_id}/{folder_name}"
            
            # Verificar si la carpeta ya existe
            try:
                self.s3_client.head_object(Bucket=self.bucket_name, Key=folder_path)
                logger.info(f"Carpeta de categoría '{folder_name}' ya existe para usuario {user_id}")
                return
            except ClientError as e:
                if e.response['Error']['Code'] == '404':
                    # La carpeta no existe, crearla
                    logger.info(f"Creando carpeta de categoría '{folder_name}' para usuario {user_id}")
                else:
                    raise
            
            # Crear la carpeta de categoría
            # Convertir categoría a ASCII seguro para metadatos de S3
            category_ascii = self._to_ascii_safe(folder_name.rstrip('/'))
            
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=folder_path,
                Body=b'',
                Metadata={
                    'user_id': user_id,
                    'created_at': datetime.utcnow().isoformat(),
                    'type': 'category_folder',
                    'category': category_ascii  # Usar versión ASCII segura
                }
            )
            
            logger.info(f"Carpeta de categoría '{folder_name}' creada exitosamente para usuario {user_id}")
            
        except Exception as e:
            logger.error(f"Error asegurando que la carpeta de categoría existe: {str(e)}")
            raise
    
    def _to_ascii_safe(self, text: str) -> str:
        """
        Convierte texto a ASCII seguro para metadatos de S3.
        Reemplaza caracteres no ASCII con equivalentes ASCII cuando es posible.
        """
        try:
            # Normalizar el texto (NFD descompone caracteres acentuados)
            normalized = unicodedata.normalize('NFD', text)
            # Eliminar marcas diacríticas (acentos) y convertir a ASCII
            ascii_text = normalized.encode('ascii', 'ignore').decode('ascii')
            # Si el texto quedó vacío después de la conversión, usar versión sanitizada
            if not ascii_text.strip():
                # Remover caracteres especiales y espacios
                ascii_text = re.sub(r'[^a-zA-Z0-9\-_\s]', '', text)
                ascii_text = re.sub(r'\s+', '_', ascii_text.strip())
            # Limitar longitud y limpiar espacios múltiples
            ascii_text = re.sub(r'\s+', ' ', ascii_text.strip())
            return ascii_text[:100] if len(ascii_text) > 100 else ascii_text
        except Exception as e:
            logger.warning(f"Error convirtiendo a ASCII, usando versión sanitizada: {e}")
            # Fallback: sanitizar completamente
            sanitized = re.sub(r'[^a-zA-Z0-9\-_\s]', '', text)
            return re.sub(r'\s+', '_', sanitized.strip())[:100]
    
    def _sanitize_folder_name(self, folder_name: str) -> str:
        """
        Sanitizar nombre de carpeta para S3 (igual que aws_service._sanitize_folder_name)
        Primero convierte a ASCII (elimina acentos), luego reemplaza espacios con guiones bajos.
        Ejemplo: "Recibo Eléctrico" -> "Recibo_Electrico"
        """
        try:
            # Primero convertir a ASCII seguro (elimina acentos: "ó" -> "o")
            # Normalizar el texto (NFD descompone caracteres acentuados)
            normalized = unicodedata.normalize('NFD', folder_name)
            # Eliminar marcas diacríticas (acentos) y convertir a ASCII
            ascii_name = normalized.encode('ascii', 'ignore').decode('ascii')
            
            # Si el texto quedó vacío, usar el nombre original
            if not ascii_name.strip():
                ascii_name = folder_name
            
            # Luego reemplazar espacios con guiones bajos y limpiar caracteres especiales
            sanitized = re.sub(r'[^a-zA-Z0-9\-_]', '_', ascii_name)
            # Limitar longitud
            return sanitized[:50]
        except Exception as e:
            logger.warning(f"Error sanitizando nombre de carpeta, usando versión básica: {e}")
            # Fallback: sanitización básica
            sanitized = re.sub(r'[^a-zA-Z0-9\-_]', '_', folder_name)
            return sanitized[:50]
    
    def _determine_folder_by_type(self, content_type: str) -> str:
        """
        Determina la carpeta basada en el tipo de contenido
        """
        if content_type.startswith('image/'):
            return 'images/'
        elif content_type == 'application/pdf':
            return 'pdfs/'
        elif 'contract' in content_type or 'agreement' in content_type:
            return 'contracts/'
        elif 'invoice' in content_type or 'bill' in content_type:
            return 'invoices/'
        elif 'certificate' in content_type or 'diploma' in content_type:
            return 'certificates/'
        else:
            return 'other/'
    
    async def get_storage_usage(self, user_id: str) -> Dict[str, Any]:
        """
        Obtiene el uso de almacenamiento del usuario
        """
        try:
            prefix = f"users/{user_id}/"
            
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix
            )
            
            total_size = 0
            file_count = 0
            
            for obj in response.get('Contents', []):
                if not obj['Key'].endswith('/'):  # Solo archivos, no carpetas
                    total_size += obj['Size']
                    file_count += 1
            
            return {
                'total_size_bytes': total_size,
                'total_size_mb': round(total_size / (1024 * 1024), 2),
                'file_count': file_count,
                'storage_limit_mb': 1000,  # 1GB por defecto
                'usage_percentage': round((total_size / (1024 * 1024 * 1024)) * 100, 2)
            }
            
        except Exception as e:
            logger.error(f"Error obteniendo uso de almacenamiento: {str(e)}")
            raise

    async def list_folders(self, prefix: str = "") -> List[Dict[str, Any]]:
        """
        Lista todas las carpetas (prefijos) en S3 para un usuario específico
        """
        try:
            folders = []
            paginator = self.s3_client.get_paginator('list_objects_v2')
            
            # Asegurar que el bucket existe
            await self.ensure_bucket_exists()
            
            # Listar objetos con el prefijo especificado
            page_iterator = paginator.paginate(
                Bucket=self.bucket_name,
                Prefix=prefix,
                Delimiter='/'
            )
            
            for page in page_iterator:
                # Obtener carpetas (prefijos comunes)
                if 'CommonPrefixes' in page:
                    for folder in page['CommonPrefixes']:
                        folder_name = folder['Prefix']
                        if folder_name.endswith('/'):
                            folder_name = folder_name[:-1]  # Quitar la barra final
                        
                        # Contar documentos en esta carpeta
                        doc_count = await self._count_documents_in_folder(folder['Prefix'])
                        
                        folders.append({
                            'name': folder_name,
                            'document_count': doc_count,
                            'path': folder['Prefix']
                        })
            
            return folders
            
        except Exception as e:
            logger.error(f"Error listando carpetas: {str(e)}")
            return []

    async def _count_documents_in_folder(self, folder_prefix: str) -> int:
        """
        Cuenta los documentos en una carpeta específica
        """
        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=folder_prefix,
                MaxKeys=1000  # Límite para evitar paginación
            )
            
            # Filtrar solo archivos (no carpetas)
            files = [obj for obj in response.get('Contents', []) 
                    if not obj['Key'].endswith('/')]
            
            return len(files)
            
        except Exception as e:
            logger.error(f"Error contando documentos en carpeta {folder_prefix}: {str(e)}")
            return 0