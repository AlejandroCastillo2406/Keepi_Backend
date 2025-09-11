from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.security import HTTPBearer
from typing import List, Optional
import logging
from app.services.s3_service import S3Service
from app.services.drive_service import GoogleDriveService
from app.services.ocr_service import OCRService
from app.services.comprehend_service import ComprehendService
from app.models.user import User
from app.utils.auth import get_current_user
from app.config.database import get_db
from sqlalchemy.orm import Session

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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Configura el tipo de almacenamiento en la nube para el usuario
    """
    try:
        if storage_type not in ["keepi_cloud", "google_drive"]:
            raise HTTPException(status_code=400, detail="Tipo de almacenamiento no válido")
        
        # Actualizar preferencia del usuario
        current_user.storage_preference = storage_type
        db.commit()
        
        # Si es Keepi Cloud, crear carpeta del usuario
        if storage_type == "keepi_cloud":
            result = await s3_service.create_user_folder(str(current_user.id))
            if not result['success']:
                raise HTTPException(status_code=500, detail="Error creando carpeta de usuario")
        
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
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
        
        # Guardar metadatos en la base de datos
        from app.models.document import Document
        document = Document(
            user_id=current_user.id,
            filename=file.filename,
            file_path=upload_result['file_path'],
            file_size=upload_result.get('size', 0),
            content_type=file.content_type,
            storage_type=current_user.storage_preference,
            folder=folder or 'other',
            extracted_text=ocr_metadata['extracted_text'],
            document_type=ocr_metadata['document_type'],
            category=categorization['category'],
            tags=categorization['tags'],
            key_dates=ocr_metadata['key_dates'],
            key_numbers=ocr_metadata['key_numbers'],
            has_signature=ocr_metadata['has_signature'],
            has_tables=ocr_metadata['has_tables'],
            has_forms=ocr_metadata['has_forms'],
            confidence_score=categorization['confidence']
        )
        
        db.add(document)
        db.commit()
        db.refresh(document)
        
        return {
            "success": True,
            "document_id": document.id,
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Obtiene la lista de documentos del usuario
    """
    try:
        from app.models.document import Document
        
        query = db.query(Document).filter(Document.user_id == current_user.id)
        
        if folder:
            query = query.filter(Document.folder == folder)
        
        if category:
            query = query.filter(Document.category == category)
        
        documents = query.all()
        
        return {
            "success": True,
            "documents": [
                {
                    "id": doc.id,
                    "filename": doc.filename,
                    "category": doc.category,
                    "tags": doc.tags,
                    "folder": doc.folder,
                    "file_size": doc.file_size,
                    "created_at": doc.created_at.isoformat(),
                    "document_type": doc.document_type,
                    "has_signature": doc.has_signature,
                    "has_tables": doc.has_tables,
                    "has_forms": doc.has_forms,
                    "confidence_score": doc.confidence_score
                }
                for doc in documents
            ]
        }
        
    except Exception as e:
        logger.error(f"Error obteniendo documentos: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/folders")
async def get_folders(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
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
            folder_id = await drive_service.create_folder(folder_name, parent_id)
            
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
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Descarga un documento
    """
    try:
        from app.models.document import Document
        
        document = db.query(Document).filter(
            Document.id == document_id,
            Document.user_id == current_user.id
        ).first()
        
        if not document:
            raise HTTPException(status_code=404, detail="Documento no encontrado")
        
        if document.storage_type == "keepi_cloud":
            result = await s3_service.download_document(
                str(current_user.id),
                document.file_path
            )
        else:  # google_drive
            # TODO: Implementar descarga de Google Drive
            result = {
                'success': True,
                'signed_url': f"https://drive.google.com/file/{document.file_path}",
                'filename': document.filename
            }
        
        return result
        
    except Exception as e:
        logger.error(f"Error descargando documento: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/delete-document/{document_id}")
async def delete_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Elimina un documento
    """
    try:
        from app.models.document import Document
        
        document = db.query(Document).filter(
            Document.id == document_id,
            Document.user_id == current_user.id
        ).first()
        
        if not document:
            raise HTTPException(status_code=404, detail="Documento no encontrado")
        
        # Eliminar del almacenamiento
        if document.storage_type == "keepi_cloud":
            await s3_service.delete_document(
                str(current_user.id),
                document.file_path
            )
        else:  # google_drive
            # TODO: Implementar eliminación de Google Drive
            pass
        
        # Eliminar de la base de datos
        db.delete(document)
        db.commit()
        
        return {
            "success": True,
            "message": "Documento eliminado exitosamente"
        }
        
    except Exception as e:
        logger.error(f"Error eliminando documento: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/storage-usage")
async def get_storage_usage(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Cambia el tipo de almacenamiento del usuario
    """
    try:
        if new_storage_type not in ["keepi_cloud", "google_drive"]:
            raise HTTPException(status_code=400, detail="Tipo de almacenamiento no válido")
        
        # Actualizar preferencia del usuario
        current_user.storage_preference = new_storage_type
        db.commit()
        
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

@router.get("/storage-status")
async def get_storage_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
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
