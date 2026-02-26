from typing import Optional, List, Dict, Any, TYPE_CHECKING
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
import logging

from app.config.database import get_db, DatabaseConfig
from app.models.document import Document, DocumentCreate as ModelDocumentCreate, DocumentUpdate as ModelDocumentUpdate, DocumentResponse as ModelDocumentResponse
from app.models.folder import Folder

DocumentCreate = ModelDocumentCreate
DocumentResponse = ModelDocumentResponse

from app.services.aws import AWSService, DocumentAnalysisService
from app.services.almacenamiento import FolderService
from app.services.usuarios import UserConfigService

if TYPE_CHECKING:
    from app.interfaces.repositories.document_repository import IDocumentRepository

logger = logging.getLogger(__name__)


def _response_from_orm(doc: Document):
    """Usa el DTO de respuesta del modelo actual para compatibilidad."""
    return ModelDocumentResponse.from_orm(doc)


def _get_or_create_folder(db: Session, user_id: str, category: str, drive_folder_id: str) -> Folder:
    """Obtiene o crea un Folder por user_id, category y drive_folder_id."""
    import uuid
    folder = db.query(Folder).filter(
        Folder.user_id == uuid.UUID(user_id) if isinstance(user_id, str) else user_id,
        Folder.drive_folder_id == drive_folder_id,
    ).first()
    if folder:
        return folder
    folder = Folder(
        user_id=uuid.UUID(user_id) if isinstance(user_id, str) else user_id,
        name=category,
        category=category,
        drive_folder_id=drive_folder_id,
        drive_parent_id=None,
    )
    db.add(folder)
    db.commit()
    db.refresh(folder)
    return folder


class DocumentService:
    """Servicio para gestión de documentos. Acepta repositorio inyectado para CRUD (testeable)."""

    def __init__(self, db: Session = None, document_repository: "IDocumentRepository | None" = None):
        self.db = db or next(get_db())
        self._document_repository = document_repository
        self.aws_service = AWSService()
        self.user_config_service = UserConfigService()
        self.folder_service = FolderService()
        self.ai_analysis_service = DocumentAnalysisService()

    async def get_user_documents(self, user_id: str) -> List[ModelDocumentResponse]:
        """Obtener todos los documentos de un usuario."""
        try:
            if self._document_repository:
                documents = self._document_repository.get_by_user_id(user_id)
                return [_response_from_orm(doc) for doc in documents]
            documents = self.db.query(Document).filter(Document.user_id == user_id).all()
            return [_response_from_orm(doc) for doc in documents]
        except Exception as e:
            logger.exception("Error obteniendo documentos")
            return []

    async def get_document_by_id(self, document_id: str, user_id: str) -> Optional[ModelDocumentResponse]:
        """Obtener documento por ID."""
        try:
            if self._document_repository:
                document = self._document_repository.get_by_id(document_id, user_id)
                return _response_from_orm(document) if document else None
            document = self.db.query(Document).filter(
                Document.id == document_id,
                Document.user_id == user_id,
            ).first()
            return _response_from_orm(document) if document else None
        except Exception as e:
            logger.exception("Error obteniendo documento")
            return None

    async def create_document(self, user_id: str, document_data: ModelDocumentCreate) -> ModelDocumentResponse:
        """Crear nuevo documento."""
        try:
            folder_id = None
            drive_folder_id = getattr(document_data, "drive_folder_id", None)
            if drive_folder_id and document_data.category:
                folder = _get_or_create_folder(
                    self.db, user_id, document_data.category, drive_folder_id
                )
                folder_id = folder.id
            if self._document_repository:
                data_to_pass = document_data.model_copy(
                    update={"folder_id": str(folder_id) if folder_id else None}
                )
                doc = self._document_repository.create(user_id, data_to_pass)
                return _response_from_orm(doc)
            document = Document(
                user_id=user_id,
                name=document_data.name,
                category=document_data.category,
                description=document_data.description,
                file_url=document_data.file_url,
                file_name=document_data.file_name,
                file_size=document_data.file_size,
                file_type=document_data.file_type,
                expiry_date=document_data.expiry_date,
                document_metadata=document_data.document_metadata or {},
                tags=document_data.tags or [],
                drive_file_id=document_data.drive_file_id,
                cloud_provider=document_data.cloud_provider,
                s3_key=document_data.s3_key,
                extracted_text=document_data.extracted_text,
                ai_analysis=document_data.ai_analysis or {},
                folder_id=folder_id,
            )
            self.db.add(document)
            self.db.commit()
            self.db.refresh(document)
            return _response_from_orm(document)
        except Exception as e:
            logger.exception("Error creando documento")
            self.db.rollback()
            raise

    async def update_document(
        self, document_id: str, user_id: str, document_data: ModelDocumentUpdate
    ) -> Optional[ModelDocumentResponse]:
        """Actualizar documento."""
        try:
            if self._document_repository:
                doc = self._document_repository.update(document_id, user_id, document_data)
                return _response_from_orm(doc) if doc else None
            document = self.db.query(Document).filter(
                Document.id == document_id,
                Document.user_id == user_id,
            ).first()
            if not document:
                return None
            update_data = document_data.dict(exclude_unset=True)
            for field, value in update_data.items():
                setattr(document, field, value)
            self.db.commit()
            self.db.refresh(document)
            return _response_from_orm(document)
        except Exception as e:
            logger.exception("Error actualizando documento")
            self.db.rollback()
            return None

    async def delete_document(self, document_id: str, user_id: str) -> bool:
        """Eliminar documento."""
        try:
            if self._document_repository:
                return self._document_repository.delete(document_id, user_id)
            document = self.db.query(Document).filter(
                Document.id == document_id,
                Document.user_id == user_id,
            ).first()
            if not document:
                return False
            self.db.delete(document)
            self.db.commit()
            return True
        except Exception as e:
            logger.exception("Error eliminando documento")
            self.db.rollback()
            return False
    
    async def get_document_categories(self, user_id: str) -> List[str]:
        """Obtener categorías de documentos del usuario"""
        try:
            documents = self.db.query(Document.category).filter(Document.user_id == user_id).distinct().all()
            return [category[0] for category in documents]
        except Exception as e:
            print(f"Error obteniendo categorías: {e}")
            return []
    
    async def get_expiring_documents(self, user_id: str, days: int = 30) -> List[DocumentResponse]:
        """Obtener documentos que vencen pronto"""
        try:
            cutoff_date = datetime.now() + timedelta(days=days)
            documents = self.db.query(Document).filter(
                Document.user_id == user_id,
                Document.expiry_date.isnot(None),
                Document.expiry_date <= cutoff_date
            ).all()
            
            return [DocumentResponse.from_orm(doc) for doc in documents]
        except Exception as e:
            print(f"Error obteniendo documentos por vencer: {e}")
            return []
    
    async def search_documents(self, user_id: str, query: str) -> List[DocumentResponse]:
        """Buscar documentos por texto"""
        try:
            query_lower = f"%{query.lower()}%"
            documents = self.db.query(Document).filter(
                Document.user_id == user_id,
                (Document.name.ilike(query_lower) |
                 Document.description.ilike(query_lower) |
                 Document.category.ilike(query_lower))
            ).all()
            
            return [DocumentResponse.from_orm(doc) for doc in documents]
        except Exception as e:
            print(f"Error buscando documentos: {e}")
            return []
    
    async def process_document_with_bedrock(self, user_id: str, file_data: bytes, file_name: str, file_type: str) -> DocumentResponse:
        """Procesar documento con Bedrock y crear carpetas automáticamente"""
        try:
            # Obtener configuración del usuario
            user_config = await self.user_config_service.get_user_config(user_id)
            storage_preference = user_config.cloud_provider.value if user_config and user_config.cloud_provider else "keepi_cloud"
            
            # PASO 1: Análisis con Bedrock (verificando límites de suscripción)
            ai_analysis = await self.ai_analysis_service.analyze_document(file_data, file_type, file_name, user_id, self.db)
            
            # Verificar si requiere suscripción
            if ai_analysis.get('suggested_category') == "SUBSCRIPTION_REQUIRED":
                # Devolver error de suscripción requerida
                from fastapi import HTTPException
                raise HTTPException(
                    status_code=402,  # Payment Required
                    detail={
                        "error": "subscription_required",
                        "message": ai_analysis.get('subscription_required_message', 'Suscripción requerida'),
                        "subscription_info": ai_analysis.get('subscription_info', {}),
                        "code": "SUBSCRIPTION_REQUIRED"
                    }
                )
            
            # Verificar si requiere clasificación manual
            if ai_analysis.get('suggested_category') == "MANUAL_CLASSIFICATION_REQUIRED":
                # Crear documento con categoría pendiente
                document_data = DocumentCreate(
                    name=file_name,
                    category="Pendiente de clasificación",
                    file_name=file_name,
                    file_type=file_type,
                    file_size=len(file_data),
                    file_url=None,
                    cloud_provider=storage_preference,
                    s3_key=None,
                    extracted_text=ai_analysis.get('extracted_text', ''),
                    ai_analysis=ai_analysis,
                    expiry_date=ai_analysis.get('expiry_date'),
                    document_number=ai_analysis.get('document_number'),
                    organization=ai_analysis.get('organization')
                )
                
                return await self.create_document(user_id, document_data)
            
            # PASO 2: Obtener categoría y fecha de vencimiento de Bedrock
            category = ai_analysis.get('suggested_category', 'Documento')
            expiry_date = ai_analysis.get('expiry_date')
            confidence = ai_analysis.get('confidence_score', 0.5)
            
            # PASO 3: Crear carpeta de categoría automáticamente
            folder_result = await self.folder_service.ensure_category_folder_exists(
                user_id, category, storage_preference
            )
            
            if not folder_result.get('success'):
                # Si requiere autorización de Drive, lanzar excepción especial
                if folder_result.get('requires_drive_auth'):
                    from app.exceptions import DriveAuthRequiredException
                    raise DriveAuthRequiredException(
                        message=folder_result.get('error', 'Se requiere autorización de Google Drive'),
                        drive_auth_url=folder_result.get('drive_auth_url', '')
                    )
                else:
                    print(f"⚠️ Error creando carpeta de categoría: {folder_result.get('error')}")
                    # Continuar sin carpeta específica
            
            # PASO 4: Subir archivo a la carpeta de categoría
            file_url = None
            s3_key = None
            drive_file_id = None
            drive_folder_id = None
            
            if storage_preference == 'keepi_cloud':
                # Subir a S3 en la carpeta de categoría
                folder_name = folder_result.get('folder_name', category)
                folder_path = f"users/{user_id}/{folder_name}/"
                
                # Subir archivo directamente a la carpeta de categoría
                file_url = await self.aws_service.upload_to_s3_with_folder(
                    file_data, file_name, user_id, folder_name
                )
                s3_key = f"{folder_path}{file_name}"
                
            elif storage_preference == 'google_drive':
                # Subir a Google Drive en la carpeta de categoría
                from app.services.autenticacion import GoogleOAuthService
                from app.services.almacenamiento import GoogleDriveService
                
                # Obtener credenciales del usuario
                oauth_service = GoogleOAuthService()
                user_credentials = await oauth_service.refresh_user_tokens(user_id)
                
                if not user_credentials:
                    from fastapi import HTTPException
                    raise HTTPException(
                        status_code=401,
                        detail="Usuario no ha autorizado acceso a Google Drive. Use /api/v1/auth/google/authorize primero."
                    )
                
                # Crear servicio de Drive con las credenciales del usuario
                drive_service = GoogleDriveService(user_credentials)
                drive_folder_id = folder_result.get('folder_id')
                
                # Verificar que tenemos un folder_id válido
                if not drive_folder_id:
                    # Si no hay folder_id en el resultado, intentar crear la carpeta de nuevo
                    logger.warning(f"⚠️ No se obtuvo folder_id para categoría '{category}', creando carpeta...")
                    folder_creation = await self.folder_service.create_category_folder(
                        user_id, category, storage_preference
                    )
                    drive_folder_id = folder_creation.get('folder_id')
                    
                    # Si aún no hay folder_id, usar General como fallback
                    if not drive_folder_id:
                        logger.warning(f"⚠️ No se pudo crear carpeta para '{category}', usando General como fallback")
                        drive_folder_id = await drive_service.get_or_create_folder("General")
                        category = "General"  # Actualizar categoría para consistencia
                
                # Subir archivo directamente a la carpeta de categoría
                logger.info(f"📁 Subiendo archivo '{file_name}' a carpeta '{category}' (ID: {drive_folder_id})")
                drive_file_id = await drive_service.upload_file(
                    file_data, 
                    file_name, 
                    drive_folder_id, 
                    file_type
                )
                logger.info(f"✅ Archivo subido exitosamente a Google Drive (File ID: {drive_file_id})")
                
                # Obtener URL del archivo
                file_url = await drive_service.get_file_download_url(drive_file_id)
                if not file_url:
                    # Fallback: construir URL manualmente
                    file_url = f"https://drive.google.com/file/d/{drive_file_id}/view"
                
                s3_key = f"drive/{drive_folder_id}/{drive_file_id}"
            
            # PASO 5: Crear documento en base de datos
            document_data = DocumentCreate(
                name=file_name,
                category=category,
                file_name=file_name,
                file_type=file_type,
                file_size=len(file_data),
                file_url=file_url,
                cloud_provider=storage_preference,
                s3_key=s3_key,
                extracted_text=ai_analysis.get('extracted_text', ''),
                ai_analysis=ai_analysis,
                expiry_date=expiry_date,
                document_number=ai_analysis.get('document_number'),
                organization=ai_analysis.get('organization'),
                tags=ai_analysis.get('tags', []),
                # Agregar IDs de Google Drive si se usó
                drive_file_id=drive_file_id,
                drive_folder_id=drive_folder_id
            )
            
            return await self.create_document(user_id, document_data)
            
        except Exception as e:
            print(f"Error procesando documento con Bedrock: {e}")
            raise

    async def _get_existing_folder_names(self, user_id: str) -> List[str]:
        """Obtiene los nombres de carpetas existentes del usuario (Drive) para pasarlos al prompt de análisis."""
        try:
            from app.models.user_config import CloudProvider
            from app.services.almacenamiento import GoogleDriveService
            from app.services.autenticacion import GoogleOAuthService
            user_config = await self.user_config_service.get_user_config(user_id)
            if not user_config or user_config.cloud_provider != CloudProvider.GOOGLE_DRIVE:
                return []
            oauth = GoogleOAuthService()
            credentials = await oauth.refresh_user_tokens(user_id)
            if not credentials:
                return []
            drive = GoogleDriveService(credentials)
            folders = await drive.get_folder_structure()
            return [f["name"] for f in folders if f.get("name")]
        except Exception as e:
            logger.warning("No se pudieron listar carpetas existentes para análisis: %s", e)
            return []

    async def analyze_document_only(
        self, user_id: str, file_data: bytes, file_name: str, file_type: str
    ) -> Dict[str, Any]:
        """Solo analizar documento con Bedrock. No guarda ni sube. Para flujo móvil en 2 pasos."""
        import re
        logger.info("analyze_document_only: usuario=%s, archivo=%s, tamaño=%s bytes", user_id, file_name, len(file_data))
        existing_folders = await self._get_existing_folder_names(user_id)
        ai_analysis = await self.ai_analysis_service.analyze_document(
            file_data, file_type, file_name, user_id, self.db, existing_category_names=existing_folders
        )
        if ai_analysis.get("suggested_category") == "SUBSCRIPTION_REQUIRED":
            return {
                "subscription_required": True,
                "message": ai_analysis.get("subscription_required_message", "Suscripción requerida"),
                "subscription_info": ai_analysis.get("subscription_info", {}),
            }
        if ai_analysis.get("suggested_category") == "MANUAL_CLASSIFICATION_REQUIRED":
            return {
                "manual_classification_required": True,
                "message": ai_analysis.get("manual_classification_message", "Clasificación manual"),
                "category": "Pendiente de clasificación",
                "recommended_name": file_name,
                "expiry_date": None,
                "tags": ai_analysis.get("tags", []),
                "confidence_score": 0,
            }
        category = ai_analysis.get("suggested_category", "Documento")
        recommended_name = ai_analysis.get("recommended_name")
        if not recommended_name or not recommended_name.strip():
            safe_cat = re.sub(r"[^\w\s\-]", "", category).strip().replace(" ", "_")[:40]
            base = file_name.rsplit(".", 1)[0] if "." in file_name else file_name
            ext = file_name.rsplit(".", 1)[-1] if "." in file_name else ""
            recommended_name = f"{safe_cat}_{base}.{ext}" if ext else f"{safe_cat}_{base}"
        else:
            recommended_name = recommended_name.strip()
        return {
            "category": category,
            "recommended_name": recommended_name,
            "expiry_date": ai_analysis.get("expiry_date"),
            "tags": ai_analysis.get("tags", []),
            "confidence_score": ai_analysis.get("confidence_score", 0.5),
            "manual_classification_required": False,
            "subscription_required": False,
            "subscription_info": ai_analysis.get("subscription_info"),
        }

    async def save_analyzed_document(
        self,
        user_id: str,
        file_data: bytes,
        file_name: str,
        file_type: str,
        category: str,
        save_as_name: str,
        expiry_date: Optional[datetime] = None,
        document_number: Optional[str] = None,
        organization: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> ModelDocumentResponse:
        """Guardar documento ya analizado: crear carpeta de categoría si no existe (categoría normalizada), subir archivo y crear registro."""
        category = category.strip().title() if category else category
        user_config = await self.user_config_service.get_user_config(user_id)
        storage_preference = (
            user_config.cloud_provider.value if user_config and user_config.cloud_provider else "keepi_cloud"
        )
        folder_result = await self.folder_service.ensure_category_folder_exists(
            user_id, category, storage_preference
        )
        if not folder_result.get("success"):
            if folder_result.get("requires_drive_auth"):
                from app.exceptions import DriveAuthRequiredException
                raise DriveAuthRequiredException(
                    message=folder_result.get("error", "Se requiere autorización de Google Drive"),
                    drive_auth_url=folder_result.get("drive_auth_url", ""),
                )
            raise ValueError(folder_result.get("error", "No se pudo crear o acceder a la carpeta"))
        file_url = None
        s3_key = None
        drive_file_id = None
        drive_folder_id = None
        if storage_preference == "keepi_cloud":
            folder_name = folder_result.get("folder_name", category)
            file_url = await self.aws_service.upload_to_s3_with_folder(
                file_data, save_as_name, user_id, folder_name
            )
            s3_key = f"users/{user_id}/{folder_name}/{save_as_name}"
        elif storage_preference == "google_drive":
            from app.services.autenticacion import GoogleOAuthService
            from app.services.almacenamiento import GoogleDriveService
            oauth_service = GoogleOAuthService()
            user_credentials = await oauth_service.refresh_user_tokens(user_id)
            if not user_credentials:
                raise ValueError("Usuario no ha autorizado acceso a Google Drive")
            drive_service = GoogleDriveService(user_credentials)
            drive_folder_id = folder_result.get("folder_id")
            if not drive_folder_id:
                folder_creation = await self.folder_service.create_category_folder(
                    user_id, category, storage_preference
                )
                drive_folder_id = folder_creation.get("folder_id")
                if not drive_folder_id:
                    drive_folder_id = await drive_service.get_or_create_folder("General")
            drive_file_id = await drive_service.upload_file(
                file_data, save_as_name, drive_folder_id, file_type
            )
            file_url = f"https://drive.google.com/file/d/{drive_file_id}/view"
            s3_key = f"drive/{drive_folder_id}/{drive_file_id}"
        ai_analysis = {
            "keepi_classified": True,
        }
        document_data = DocumentCreate(
            name=save_as_name,
            category=category,
            description="Documento clasificado y guardado con Keepi",
            file_url=file_url,
            file_name=save_as_name,
            file_size=len(file_data),
            file_type=file_type,
            expiry_date=expiry_date,
            cloud_provider=storage_preference,
            s3_key=s3_key,
            ai_analysis=ai_analysis,
            tags=tags or [],
            drive_file_id=drive_file_id,
            drive_folder_id=drive_folder_id,
        )
        return await self.create_document(user_id, document_data)

    async def process_document_with_aws(self, user_id: str, file_data: bytes, file_name: str, file_type: str) -> DocumentResponse:
        """Procesar documento con AWS Textract y Comprehend - Flujo dinámico"""
        try:
            # Obtener configuración del usuario
            user_config = await self.user_config_service.get_user_config(user_id)
            cloud_provider = user_config.cloud_provider if user_config else "google_drive"
            
            # PASO 1: Subir archivo a carpeta temporal
            file_url = None
            s3_key = None
            
            if cloud_provider == "keepi_cloud":
                # Crear estructura de carpetas del usuario si no existe
                await self.aws_service.create_user_folders(user_id)
                
                # Subir a carpeta temporal
                file_url = await self.aws_service.upload_to_s3_temp(file_data, file_name, user_id)
                s3_key = f"users/{user_id}/temp/{file_name}"
            
            # PASO 2: Extraer texto de cualquier tipo de documento
            extraction_result = await self.aws_service.extract_text_from_document(file_data, file_name, file_type)
            extracted_text = extraction_result.get('text', '')
            
            # PASO 3: Categorizar con AWS Comprehend (completamente dinámico)
            ai_analysis = None
            category = 'General'
            
            print(f"🔍 DEBUG: Texto extraído: {len(extracted_text)} caracteres")
            print(f"🔍 DEBUG: Primeros 200 chars: {extracted_text[:200]}...")
            
            if extracted_text and len(extracted_text.strip()) > 10:  # Solo si hay texto significativo
                try:
                    print(f"🔍 DEBUG: Llamando a categorize_document...")
                    # Usar AWS Comprehend para análisis dinámico
                    comprehend_result = await self.aws_service.categorize_document(extracted_text)
                    print(f"🔍 DEBUG: Comprehend result: {comprehend_result.get('category', 'N/A')}")
                    ai_analysis = {
                        'extraction': extraction_result,
                        'comprehend': comprehend_result
                    }
                    
                    # Usar categoría detectada dinámicamente por AWS Comprehend
                    category = comprehend_result.get('category', 'General')
                    
                    # PASO 4: Mover archivo a carpeta de categoría correspondiente
                    if cloud_provider == "keepi_cloud":
                        # Crear carpeta de categoría si no existe
                        category_folder = await self.aws_service.create_category_folder(user_id, category)
                        
                        # Mover archivo de temp a categoría
                        new_file_url = await self.aws_service.move_file_in_s3(
                            user_id, 
                            file_name, 
                            "temp", 
                            f"categorias/{self.aws_service._sanitize_folder_name(category)}"
                        )
                        
                        # Actualizar URLs y rutas
                        file_url = new_file_url
                        s3_key = f"users/{user_id}/categorias/{self.aws_service._sanitize_folder_name(category)}/{file_name}"
                    
                except Exception as e:
                    print(f"Error en categorización: {e}")
                    ai_analysis = {
                        'extraction': extraction_result,
                        'comprehend_error': str(e)
                    }
            else:
                ai_analysis = {
                    'extraction': extraction_result,
                    'no_text_to_analyze': True
                }
                
                # Si no hay texto, mover a carpeta General
                if cloud_provider == "keepi_cloud":
                    category_folder = await self.aws_service.create_category_folder(user_id, "General")
                    new_file_url = await self.aws_service.move_file_in_s3(
                        user_id, 
                        file_name, 
                        "temp", 
                        "categorias/General"
                    )
                    file_url = new_file_url
                    s3_key = f"users/{user_id}/categorias/General/{file_name}"
            
            # PASO 5: Crear documento en base de datos
            document_data = DocumentCreate(
                name=file_name,
                category=category,
                file_name=file_name,
                file_type=file_type,
                file_size=len(file_data),
                file_url=file_url,
                cloud_provider=cloud_provider,
                s3_key=s3_key,
                extracted_text=extracted_text,
                ai_analysis=ai_analysis
            )
            
            return await self.create_document(user_id, document_data)
            
        except Exception as e:
            print(f"Error procesando documento con AWS: {e}")
            raise
