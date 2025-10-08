from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.config.database import get_db, DatabaseConfig
from app.models.document import Document, DocumentCreate, DocumentUpdate, DocumentResponse
from app.services.aws_service import AWSService
from app.services.user_config_service import UserConfigService
from app.services.folder_service import FolderService
from app.services.ai_analysis_service import DocumentAnalysisService

class DocumentService:
    """Servicio para gestión de documentos"""
    
    def __init__(self, db: Session = None):
        self.db = db or next(get_db())
        self.aws_service = AWSService()
        self.user_config_service = UserConfigService()
        self.folder_service = FolderService()
        self.ai_analysis_service = DocumentAnalysisService()
    
    async def get_user_documents(self, user_id: str) -> List[DocumentResponse]:
        """Obtener todos los documentos de un usuario"""
        try:
            documents = self.db.query(Document).filter(Document.user_id == user_id).all()
            return [DocumentResponse.from_orm(doc) for doc in documents]
        except Exception as e:
            print(f"Error obteniendo documentos: {e}")
            return []
    
    async def get_document_by_id(self, document_id: str, user_id: str) -> Optional[DocumentResponse]:
        """Obtener documento por ID"""
        try:
            document = self.db.query(Document).filter(
                Document.id == document_id,
                Document.user_id == user_id
            ).first()
            
            if document:
                return DocumentResponse.from_orm(document)
            return None
        except Exception as e:
            print(f"Error obteniendo documento: {e}")
            return None
    
    async def create_document(self, user_id: str, document_data: DocumentCreate) -> DocumentResponse:
        """Crear nuevo documento"""
        try:
            # Crear instancia de documento
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
                drive_folder_id=document_data.drive_folder_id,
                cloud_provider=document_data.cloud_provider,
                s3_key=document_data.s3_key,
                extracted_text=document_data.extracted_text,
                ai_analysis=document_data.ai_analysis or {}
            )
            
            self.db.add(document)
            self.db.commit()
            self.db.refresh(document)
            
            return DocumentResponse.from_orm(document)
        except Exception as e:
            print(f"Error creando documento: {e}")
            self.db.rollback()
            raise
    
    async def update_document(self, document_id: str, user_id: str, document_data: DocumentUpdate) -> Optional[DocumentResponse]:
        """Actualizar documento"""
        try:
            document = self.db.query(Document).filter(
                Document.id == document_id,
                Document.user_id == user_id
            ).first()
            
            if not document:
                return None
            
            # Actualizar campos
            update_data = document_data.dict(exclude_unset=True)
            for field, value in update_data.items():
                setattr(document, field, value)
            
            self.db.commit()
            self.db.refresh(document)
            
            return DocumentResponse.from_orm(document)
        except Exception as e:
            print(f"Error actualizando documento: {e}")
            self.db.rollback()
            return None
    
    async def delete_document(self, document_id: str, user_id: str) -> bool:
        """Eliminar documento"""
        try:
            document = self.db.query(Document).filter(
                Document.id == document_id,
                Document.user_id == user_id
            ).first()
            
            if not document:
                return False
            
            self.db.delete(document)
            self.db.commit()
            return True
        except Exception as e:
            print(f"Error eliminando documento: {e}")
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
                folder_id = folder_result.get('folder_id')
                file_url = await self.drive_service.upload_file(file_data, file_name, folder_id)
                s3_key = f"drive/{folder_id}/{file_name}"
            
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
                tags=ai_analysis.get('tags', [])
            )
            
            return await self.create_document(user_id, document_data)
            
        except Exception as e:
            print(f"Error procesando documento con Bedrock: {e}")
            raise
    
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
