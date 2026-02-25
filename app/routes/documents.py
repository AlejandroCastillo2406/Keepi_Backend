from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File, Form
from typing import List, Optional, Dict, Any
import tempfile
import os
from datetime import datetime
from fastapi.responses import JSONResponse

from app.core.security import verify_token
from app.services.documento import DocumentService
from app.services.almacenamiento import GoogleDriveService
from app.services.aws import DocumentAnalysisService
from app.models.document import DocumentCreate, DocumentUpdate, DocumentResponse
from app.routes.dependencies import get_document_service

router = APIRouter()


@router.get("/", response_model=List[DocumentResponse])
async def get_documents(
    user_token: dict = Depends(verify_token),
    document_service: DocumentService = Depends(get_document_service),
):
    """Obtener todos los documentos del usuario autenticado."""
    try:
        documents = await document_service.get_user_documents(user_token["uid"])
        return documents
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: str,
    user_token: dict = Depends(verify_token),
    document_service: DocumentService = Depends(get_document_service),
):
    """Obtener documento específico por ID."""
    try:
        document = await document_service.get_document_by_id(document_id, user_token["uid"])
        if not document:
            raise HTTPException(status_code=404, detail="Documento no encontrado")
        return document
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/", response_model=DocumentResponse)
async def create_document(
    document_data: DocumentCreate,
    user_token: dict = Depends(verify_token),
    document_service: DocumentService = Depends(get_document_service),
):
    """Crear nuevo documento."""
    try:
        document = await document_service.create_document(user_token["uid"], document_data)
        return document
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

@router.post("/upload")
@router.post("/upload_and_analyze_document")  # Alias para compatibilidad con tests
async def upload_and_analyze_document(
    file: UploadFile = File(...),
    user_token: dict = Depends(verify_token)
):
    """Subir archivo, analizarlo con Bedrock y crear carpetas automáticamente"""
    try:
        # Verificar tipo de archivo
        if not file.filename:
            raise HTTPException(status_code=400, detail="Nombre de archivo requerido")
        
        # Leer contenido del archivo
        content = await file.read()
        
        # Procesar documento con Bedrock
        document_service = DocumentService()
        document = await document_service.process_document_with_bedrock(
            user_token['uid'],
            content,
            file.filename,
            file.content_type or "application/octet-stream"
        )
        
        # Si requiere clasificación manual, devolver respuesta especial
        if document.category == "Pendiente de clasificación":
            return {
                "requires_manual_classification": True,
                "message": "No pudimos clasificarlo de manera adecuada, ¿a qué categoría corresponde?",
                "filename": file.filename,
                "file_type": file.content_type,
                "file_size": len(content),
                "document_id": document.id
            }
        
        return {
            "message": "Documento subido y analizado exitosamente con Bedrock",
            "document": document,
            "category": document.category,
            "expiry_date": document.expiry_date,
            "confidence": document.ai_analysis.get('confidence_score', 0) if document.ai_analysis else 0,
            "subscription_info": document.ai_analysis.get('subscription_info') if document.ai_analysis else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        # Verificar si es una excepción de autorización de Drive
        if "DriveAuthRequiredException" in str(type(e)) or "requires_drive_auth" in str(e):
            from app.exceptions import DriveAuthRequiredException
            if isinstance(e, DriveAuthRequiredException):
                return {
                    "requires_drive_auth": True,
                    "message": e.message,
                    "drive_auth_url": e.drive_auth_url,
                    "error": "Se requiere autorización de Google Drive"
                }
            else:
                return {
                    "requires_drive_auth": True,
                    "message": "Se requiere autorización de Google Drive",
                    "drive_auth_url": "https://accounts.google.com/oauth/authorize?client_id=YOUR_CLIENT_ID&redirect_uri=YOUR_REDIRECT_URI&scope=https://www.googleapis.com/auth/drive&response_type=code&access_type=offline",
                    "error": str(e)
                }
        else:
            raise HTTPException(status_code=500, detail=str(e))

@router.put("/{document_id}", response_model=DocumentResponse)
async def update_document(
    document_id: str,
    document_data: DocumentUpdate,
    user_token: dict = Depends(verify_token),
    document_service: DocumentService = Depends(get_document_service),
):
    """Actualizar documento existente."""
    try:
        document = await document_service.update_document(
            document_id, user_token["uid"], document_data
        )
        if not document:
            raise HTTPException(status_code=404, detail="Documento no encontrado")
        return document
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{document_id}")
async def delete_document(
    document_id: str,
    user_token: dict = Depends(verify_token),
    document_service: DocumentService = Depends(get_document_service),
):
    """Eliminar documento."""
    try:
        success = await document_service.delete_document(document_id, user_token["uid"])
        if not success:
            raise HTTPException(status_code=404, detail="Documento no encontrado")
        return {"message": "Documento eliminado correctamente", "document_id": document_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/categories/list")
async def get_document_categories(user_token: dict = Depends(verify_token)):
    """Obtener todas las categorías de documentos del usuario"""
    try:
        document_service = DocumentService()
        categories = await document_service.get_document_categories(user_token['uid'])
        return {"categories": categories}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/expiring/list", response_model=List[DocumentResponse])
async def get_expiring_documents(
    days: int = Query(30, description="Días para considerar como 'por vencer'"),
    user_token: dict = Depends(verify_token)
):
    """Obtener documentos que vencen pronto"""
    try:
        document_service = DocumentService()
        documents = await document_service.get_expiring_documents(user_token['uid'], days)
        return documents
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/search/list", response_model=List[DocumentResponse])
async def search_documents(
    q: str = Query(..., description="Término de búsqueda"),
    user_token: dict = Depends(verify_token)
):
    """Buscar documentos por texto"""
    try:
        document_service = DocumentService()
        documents = await document_service.search_documents(user_token['uid'], q)
        return documents
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/drive/structure")
async def get_drive_folder_structure(user_token: dict = Depends(verify_token)):
    """Obtener estructura de carpetas de Google Drive"""
    try:
        # Obtener credenciales del usuario
        from app.services.autenticacion import GoogleOAuthService
        
        oauth_service = GoogleOAuthService()
        user_credentials = await oauth_service.refresh_user_tokens(user_token['uid'])
        
        if not user_credentials:
            raise HTTPException(
                status_code=401, 
                detail="Usuario no ha autorizado acceso a Google Drive. Use /api/v1/auth/google/authorize primero."
            )
        
        # Obtener estructura real de Google Drive
        drive_service = GoogleDriveService(user_credentials)
        folders = await drive_service.get_folder_structure()
        
        # Contar archivos en cada carpeta
        for folder in folders:
            files = await drive_service.get_files_in_folder(folder['id'])
            folder['files_count'] = len(files)
        
        return {"folders": folders}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/drive/scan-unclassified")
async def scan_unclassified_documents(user_token: dict = Depends(verify_token)):
    """Escanear Google Drive para encontrar documentos no clasificados por KIPI"""
    try:
        # Obtener credenciales del usuario
        from app.services.autenticacion import GoogleOAuthService
        
        oauth_service = GoogleOAuthService()
        user_credentials = await oauth_service.refresh_user_tokens(user_token['uid'])
        
        if not user_credentials:
            raise HTTPException(
                status_code=401, 
                detail="Usuario no ha autorizado acceso a Google Drive. Use /api/v1/auth/google/authorize primero."
            )
        
        # Obtener todos los archivos de Google Drive
        drive_service = GoogleDriveService(user_credentials)
        all_files = await drive_service.get_all_files()
        
        # Filtrar archivos no clasificados por KIPI
        unclassified_files = []
        classified_files = []
        
        for file_info in all_files:
            # Verificar si el archivo tiene metadatos de KIPI
            has_keepi_metadata = (
                'keepi_classified' in file_info.get('description', '') or
                'keepi_category' in file_info.get('description', '') or
                'keepi_processed' in file_info.get('description', '') or
                file_info.get('name', '').startswith('KIPI_')
            )
            
            if has_keepi_metadata:
                classified_files.append(file_info)
            else:
                # Solo incluir archivos que KIPI puede procesar
                file_extension = file_info.get('name', '').lower().split('.')[-1]
                if file_extension in ['pdf', 'png', 'jpg', 'jpeg', 'docx', 'doc', 'xlsx', 'xls', 'pptx', 'ppt']:
                    unclassified_files.append(file_info)
        
        return {
            "unclassified_files": unclassified_files,
            "classified_files": classified_files,
            "total_files": len(all_files),
            "unclassified_count": len(unclassified_files),
            "classified_count": len(classified_files)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/drive/reclassify-batch")
async def reclassify_documents_batch(
    file_ids: List[str] = Form(...),
    user_token: dict = Depends(verify_token)
):
    """Reclasificar múltiples documentos de Google Drive con KIPI"""
    try:
        # Obtener credenciales del usuario
        from app.services.autenticacion import GoogleOAuthService
        
        oauth_service = GoogleOAuthService()
        user_credentials = await oauth_service.refresh_user_tokens(user_token['uid'])
        
        if not user_credentials:
            raise HTTPException(
                status_code=401, 
                detail="Usuario no ha autorizado acceso a Google Drive. Use /api/v1/auth/google/authorize primero."
            )
        
        drive_service = GoogleDriveService(user_credentials)
        results = []
        
        for file_id in file_ids:
            try:
                # Descargar archivo de Google Drive
                file_content, file_name, mime_type = await drive_service.download_file(file_id)
                
                # Analizar con KIPI
                ai_service = DocumentAnalysisService()
                analysis = await ai_service.analyze_document(
                    file_content, 
                    mime_type,
                    file_name
                )
                
                if analysis.get('suggested_category') == 'MANUAL_CLASSIFICATION_REQUIRED':
                    results.append({
                        'file_id': file_id,
                        'file_name': file_name,
                        'status': 'requires_manual_classification',
                        'message': analysis.get('manual_classification_message', 'Requiere clasificación manual')
                    })
                else:
                    # Crear carpeta de categoría si no existe
                    category = analysis.get('suggested_category', 'General')
                    category_folder = await drive_service.get_or_create_folder(category)
                    
                    # Mover archivo a la carpeta de categoría
                    await drive_service.move_file_to_folder(file_id, category_folder)
                    
                    # Actualizar descripción del archivo con metadatos de KIPI
                    new_description = f"KIPI_CLASSIFIED|{category}|{analysis.get('confidence_score', 0):.2f}|{analysis.get('ai_model_version', '1.0.0')}"
                    await drive_service.update_file_description(file_id, new_description)
                    
                    # Crear documento en la base de datos
                    document_service = DocumentService()
                    document_data = DocumentCreate(
                        name=file_name,
                        category=category,
                        description=f"Documento reclasificado automáticamente por KIPI como: {category}",
                        file_url=f"https://drive.google.com/file/d/{file_id}/view",
                        file_name=file_name,
                        file_size=len(file_content),
                        file_type=mime_type,
                        expiry_date=analysis.get('expiry_date'),
                        metadata=analysis.get('metadata', {}),
                        tags=analysis.get('tags', [])
                    )
                    
                    document = await document_service.create_document(user_token['uid'], document_data)
                    
                    results.append({
                        'file_id': file_id,
                        'file_name': file_name,
                        'status': 'success',
                        'category': category,
                        'confidence': analysis.get('confidence_score', 0),
                        'document_id': str(document.id)
                    })
                    
            except Exception as e:
                results.append({
                    'file_id': file_id,
                    'file_name': file_name if 'file_name' in locals() else 'unknown',
                    'status': 'error',
                    'error': str(e)
                })
        
        return {
            "message": f"Procesamiento completado para {len(file_ids)} archivos",
            "results": results,
            "success_count": len([r for r in results if r['status'] == 'success']),
            "manual_count": len([r for r in results if r['status'] == 'requires_manual_classification']),
            "error_count": len([r for r in results if r['status'] == 'error'])
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/manual-classification")
async def manual_classify_document(
    file: UploadFile = File(...),
    category: str = Form(..., description="Categoría manual proporcionada por el usuario"),
    folder: Optional[str] = Form(None),
    user_token: dict = Depends(verify_token)
):
    """Clasificar manualmente un documento que no pudo ser procesado automáticamente"""
    try:
        # Verificar tipo de archivo
        if not file.filename:
            raise HTTPException(status_code=400, detail="Nombre de archivo requerido")
        
        # Leer contenido del archivo
        content = await file.read()
        
        # Crear archivo temporal
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_file.write(content)
            temp_file_path = temp_file.name
        
        try:
            # Obtener configuración de almacenamiento del usuario
            from app.services.usuarios import UserConfigService
            user_config_service = UserConfigService()
            user_config = await user_config_service.get_user_config(user_token['uid'])
            
            if not user_config or not user_config.storage_preference:
                raise HTTPException(status_code=400, detail="Usuario debe configurar preferencia de almacenamiento primero")
            
            # Crear documento con clasificación manual
            document_service = DocumentService()
            
            # Crear datos del documento con clasificación manual
            document_data = DocumentCreate(
                name=file.filename,
                category=category,
                description=f"Documento clasificado manualmente por el usuario como: {category}",
                file_name=file.filename,
                file_size=len(content),
                file_type=file.content_type or "application/octet-stream",
                metadata={"manual_classification": True, "user_provided_category": category},
                tags=[category.lower(), "manual_classification"]
            )
            
            # Subir archivo según la configuración del usuario
            if user_config.storage_preference == "keepi_cloud":
                # Subir a S3
                from app.services.aws import AWSService
                aws_service = AWSService()
                
                # Crear carpeta de categoría en S3
                await aws_service.create_category_folder(user_token['uid'], category)
                
                # Subir archivo
                file_url = await aws_service.upload_to_s3_temp(content, file.filename, user_token['uid'])
                
                # Mover a carpeta de categoría
                final_url = await aws_service.move_file_in_s3(
                    user_token['uid'], 
                    file.filename, 
                    "temp", 
                    f"categorias/{category.lower().replace(' ', '_')}"
                )
                
                document_data.file_url = final_url
                
            else:  # google_drive
                # Obtener credenciales de Google Drive
                from app.services.autenticacion import GoogleOAuthService
                oauth_service = GoogleOAuthService()
                user_credentials = await oauth_service.refresh_user_tokens(user_token['uid'])
                
                if not user_credentials:
                    raise HTTPException(
                        status_code=401, 
                        detail="Usuario no ha autorizado acceso a Google Drive. Use /api/v1/auth/google/authorize primero."
                    )
                
                # Crear carpeta en Google Drive según categoría
                drive_service = GoogleDriveService(user_credentials)
                category_folder = await drive_service.get_or_create_folder(category)
                
                # Subir archivo a Google Drive
                drive_file_id = await drive_service.upload_file(
                    temp_file_path,
                    file.filename,
                    category_folder,
                    file.content_type
                )
                
                document_data.file_url = f"https://drive.google.com/file/d/{drive_file_id}/view"
            
            # Crear documento en la base de datos
            document = await document_service.create_document(user_token['uid'], document_data)
            
            # Limpiar archivo temporal
            os.unlink(temp_file_path)
            
            return {
                "message": f"Documento clasificado manualmente como '{category}' y guardado exitosamente",
                "document": document,
                "category": category,
                "storage_location": user_config.storage_preference
            }
            
        except Exception as e:
            # Limpiar archivo temporal en caso de error
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
            raise e
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/mobile/dashboard")
async def get_mobile_dashboard(
    user_token: dict = Depends(verify_token),
    limit: int = Query(10, description="Número de documentos a mostrar")
):
    """Dashboard optimizado para móviles con información resumida"""
    try:
        from app.services.usuarios import UserService
        from app.services.almacenamiento import S3Service, GoogleDriveService

        user_service = UserService()
        user = await user_service.get_user_by_uid(user_token['uid'])
        
        if not user:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        
        # Obtener documentos recientes
        document_service = DocumentService()
        all_documents = await document_service.get_user_documents(user_token['uid'])
        
        # Documentos por vencer (próximos 30 días)
        from datetime import datetime, timedelta
        expiring_soon = []
        for doc in all_documents:
            if doc.expiry_date:
                try:
                    expiry = datetime.fromisoformat(doc.expiry_date.replace('Z', '+00:00'))
                    if expiry <= datetime.now() + timedelta(days=30):
                        expiring_soon.append(doc)
                except:
                    continue
        
        # Obtener carpetas según el almacenamiento configurado
        folders = []
        if user.storage_preference == 'keepi_cloud':
            # Leer carpetas de S3
            s3_service = S3Service()
            try:
                s3_folders = await s3_service.list_folders(f"users/{user_token['uid']}")
                folders = [
                    {
                        "id": folder['name'],
                        "name": folder['name'].split('/')[-1],  # Solo el nombre de la carpeta
                        "document_count": folder.get('document_count', 0),
                        "path": folder['name']
                    }
                    for folder in s3_folders
                ]
            except Exception as e:
                print(f"Error leyendo carpetas de S3: {e}")
                folders = []
                
        elif user.storage_preference == 'google_drive':
            # Leer carpetas de Google Drive
            try:
                from app.services.autenticacion import GoogleOAuthService
                oauth_service = GoogleOAuthService()
                credentials = await oauth_service.refresh_user_tokens(str(user.id))
                
                if not credentials:
                    print("Usuario no tiene credenciales de Google Drive configuradas")
                    folders = []
                else:
                    drive_service = GoogleDriveService(credentials)
                    drive_folders = await drive_service.list_folders()
                    folders = [
                        {
                            "id": folder['id'],
                            "name": folder['name'],
                            "document_count": folder.get('document_count', 0),
                            "path": folder.get('path', '')
                        }
                        for folder in drive_folders
                    ]
            except Exception as e:
                print(f"Error leyendo carpetas de Drive: {e}")
                folders = []
        
        return {
            "folders": folders,
            "expiring_soon_count": len(expiring_soon),
            "expiring_soon": expiring_soon[:5],  # Solo los próximos 5
            "last_updated": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/mobile/search")
async def mobile_search_documents(
    q: str = Query(..., description="Término de búsqueda"),
    category: Optional[str] = Query(None, description="Filtrar por categoría"),
    limit: int = Query(20, description="Número de resultados"),
    user_token: dict = Depends(verify_token)
):
    """Búsqueda optimizada para móviles"""
    try:
        document_service = DocumentService()
        
        # Búsqueda básica
        all_documents = await document_service.get_user_documents(user_token['uid'])
        
        # Filtrar por término de búsqueda
        filtered_docs = []
        search_terms = q.lower().split()
        
        for doc in all_documents:
            doc_text = f"{doc.name} {doc.description} {doc.category}".lower()
            if all(term in doc_text for term in search_terms):
                filtered_docs.append(doc)
        
        # Filtrar por categoría si se especifica
        if category:
            filtered_docs = [doc for doc in filtered_docs if doc.category == category]
        
        # Limitar resultados
        results = filtered_docs[:limit]
        
        return {
            "query": q,
            "category_filter": category,
            "total_found": len(filtered_docs),
            "results": results,
            "search_time": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/mobile/categories")
async def get_mobile_categories(user_token: dict = Depends(verify_token)):
    """Obtener categorías con conteos para móviles"""
    try:
        document_service = DocumentService()
        documents = await document_service.get_user_documents(user_token['uid'])
        
        categories = {}
        for doc in documents:
            category = doc.category or 'Sin categoría'
            if category not in categories:
                categories[category] = {
                    'name': category,
                    'count': 0,
                    'last_document': None
                }
            
            categories[category]['count'] += 1
            
            # Mantener el documento más reciente
            if (not categories[category]['last_document'] or 
                doc.created_at > categories[category]['last_document']['created_at']):
                categories[category]['last_document'] = {
                    'id': doc.id,
                    'name': doc.name,
                    'created_at': doc.created_at
                }
        
        # Convertir a lista y ordenar por conteo
        category_list = list(categories.values())
        category_list.sort(key=lambda x: x['count'], reverse=True)
        
        return {
            "categories": category_list,
            "total_categories": len(category_list),
            "total_documents": len(documents)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/mobile/document/{document_id}")
async def get_mobile_document(
    document_id: str,
    user_token: dict = Depends(verify_token)
):
    """Obtener documento específico optimizado para móviles"""
    try:
        document_service = DocumentService()
        document = await document_service.get_document_by_id(document_id, user_token['uid'])
        
        if not document:
            raise HTTPException(status_code=404, detail="Documento no encontrado")
        
        # Información optimizada para móviles
        return {
            "id": document.id,
            "name": document.name,
            "category": document.category,
            "description": document.description,
            "file_url": document.file_url,
            "file_type": document.file_type,
            "file_size": document.file_size,
            "expiry_date": document.expiry_date,
            "tags": document.tags,
            "created_at": document.created_at,
            "updated_at": document.updated_at,
            "metadata": document.metadata
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/mobile/quick-upload")
async def mobile_quick_upload(
    file: UploadFile = File(...),
    category: Optional[str] = Form(None),
    user_token: dict = Depends(verify_token)
):
    """Subida rápida optimizada para móviles"""
    try:
        if not file.filename:
            raise HTTPException(status_code=400, detail="Nombre de archivo requerido")
        
        content = await file.read()
        
        # Si se proporciona categoría, usar clasificación manual
        if category:
            return await manual_classify_document(file, category, None, user_token)
        
        # Si no, intentar análisis automático
        return await upload_and_analyze_document(file, user_token)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
