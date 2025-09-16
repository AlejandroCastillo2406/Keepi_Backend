from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from app.config.database import DatabaseConfig
from app.models.document import DocumentCreate, DocumentUpdate, DocumentResponse
from app.services.aws_service import AWSService
from app.services.user_config_service import UserConfigService
from app.services.folder_service import FolderService
from app.services.ai_analysis_service import DocumentAnalysisService

class DocumentService:
    """Servicio para gestión de documentos"""
    
    def __init__(self):
        self.db = DatabaseConfig.get_firestore_client()
        self.aws_service = AWSService()
        self.user_config_service = UserConfigService()
        self.folder_service = FolderService()
        self.ai_analysis_service = DocumentAnalysisService()
    
    async def get_user_documents(self, user_id: str) -> List[DocumentResponse]:
        """Obtener todos los documentos de un usuario"""
        try:
            docs = self.db.collection('documents').where('user_id', '==', user_id).stream()
            documents = []
            for doc in docs:
                doc_data = doc.to_dict()
                doc_data['id'] = doc.id
                documents.append(DocumentResponse(**doc_data))
            return documents
        except Exception as e:
            print(f"Error obteniendo documentos: {e}")
            return []
    
    async def get_document_by_id(self, document_id: str, user_id: str) -> Optional[DocumentResponse]:
        """Obtener documento por ID"""
        try:
            doc_ref = self.db.collection('documents').document(document_id)
            doc = doc_ref.get()
            
            if doc.exists:
                doc_data = doc.to_dict()
                if doc_data.get('user_id') == user_id:
                    doc_data['id'] = document_id
                    return DocumentResponse(**doc_data)
            return None
        except Exception as e:
            print(f"Error obteniendo documento: {e}")
            return None
    
    async def create_document(self, user_id: str, document_data: DocumentCreate) -> DocumentResponse:
        """Crear nuevo documento"""
        try:
            doc_dict = document_data.dict()
            doc_dict['user_id'] = user_id
            doc_dict['created_at'] = datetime.now()
            doc_dict['updated_at'] = datetime.now()
            doc_dict['is_archived'] = False
            doc_dict['is_favorite'] = False
            
            doc_ref = self.db.collection('documents').add(doc_dict)
            doc_dict['id'] = doc_ref[1].id
            
            return DocumentResponse(**doc_dict)
        except Exception as e:
            print(f"Error creando documento: {e}")
            raise
    
    async def update_document(self, document_id: str, user_id: str, document_data: DocumentUpdate) -> Optional[DocumentResponse]:
        """Actualizar documento"""
        try:
            doc_ref = self.db.collection('documents').document(document_id)
            doc = doc_ref.get()
            
            if not doc.exists:
                return None
            
            doc_data = doc.to_dict()
            if doc_data.get('user_id') != user_id:
                return None
            
            update_data = document_data.dict(exclude_unset=True)
            update_data['updated_at'] = datetime.now()
            
            doc_ref.update(update_data)
            
            # Obtener documento actualizado
            updated_doc = doc_ref.get().to_dict()
            updated_doc['id'] = document_id
            
            return DocumentResponse(**updated_doc)
        except Exception as e:
            print(f"Error actualizando documento: {e}")
            return None
    
    async def delete_document(self, document_id: str, user_id: str) -> bool:
        """Eliminar documento"""
        try:
            doc_ref = self.db.collection('documents').document(document_id)
            doc = doc_ref.get()
            
            if not doc.exists:
                return False
            
            doc_data = doc.to_dict()
            if doc_data.get('user_id') != user_id:
                return False
            
            doc_ref.delete()
            return True
        except Exception as e:
            print(f"Error eliminando documento: {e}")
            return False
    
    async def get_document_categories(self, user_id: str) -> List[str]:
        """Obtener categorías de documentos del usuario"""
        try:
            docs = self.db.collection('documents').where('user_id', '==', user_id).stream()
            categories = set()
            for doc in docs:
                doc_data = doc.to_dict()
                if doc_data.get('category'):
                    categories.add(doc_data['category'])
            return list(categories)
        except Exception as e:
            print(f"Error obteniendo categorías: {e}")
            return []
    
    async def get_expiring_documents(self, user_id: str, days: int = 30) -> List[DocumentResponse]:
        """Obtener documentos que vencen pronto"""
        try:
            docs = self.db.collection('documents').where('user_id', '==', user_id).stream()
            expiring_docs = []
            cutoff_date = datetime.now() + timedelta(days=days)
            
            for doc in docs:
                doc_data = doc.to_dict()
                if doc_data.get('expiry_date'):
                    try:
                        expiry_date = datetime.fromisoformat(doc_data['expiry_date'].replace('Z', '+00:00'))
                        if expiry_date <= cutoff_date:
                            doc_data['id'] = doc.id
                            expiring_docs.append(DocumentResponse(**doc_data))
                    except ValueError:
                        continue
            
            return expiring_docs
        except Exception as e:
            print(f"Error obteniendo documentos por vencer: {e}")
            return []
    
    async def search_documents(self, user_id: str, query: str) -> List[DocumentResponse]:
        """Buscar documentos por texto"""
        try:
            docs = self.db.collection('documents').where('user_id', '==', user_id).stream()
            matching_docs = []
            query_lower = query.lower()
            
            for doc in docs:
                doc_data = doc.to_dict()
                # Buscar en nombre, descripción y categoría
                if (query_lower in doc_data.get('name', '').lower() or
                    query_lower in doc_data.get('description', '').lower() or
                    query_lower in doc_data.get('category', '').lower()):
                    doc_data['id'] = doc.id
                    matching_docs.append(DocumentResponse(**doc_data))
            
            return matching_docs
        except Exception as e:
            print(f"Error buscando documentos: {e}")
            return []
    
    async def process_document_with_bedrock(self, user_id: str, file_data: bytes, file_name: str, file_type: str) -> DocumentResponse:
        """Procesar documento con Bedrock y crear carpetas automáticamente"""
        try:
            # Obtener configuración del usuario
            user_config = await self.user_config_service.get_user_config(user_id)
            storage_preference = user_config.storage_preference if user_config else "keepi_cloud"
            
            # PASO 1: Análisis con Bedrock
            ai_analysis = await self.ai_analysis_service.analyze_document(file_data, file_type, file_name)
            
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
                print(f"⚠️ Error creando carpeta de categoría: {folder_result.get('error')}")
                # Continuar sin carpeta específica
            
            # PASO 4: Subir archivo a la carpeta de categoría
            file_url = None
            s3_key = None
            
            if storage_preference == 'keepi_cloud':
                # Subir a S3 en la carpeta de categoría
                folder_path = f"users/{user_id}/{folder_result.get('folder_name', category)}/"
                file_url = await self.aws_service.upload_to_s3(file_data, file_name, folder_path)
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
