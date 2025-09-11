from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from typing import List, Optional, Dict, Any
import tempfile
import os
from datetime import datetime

from app.utils.auth import verify_token
from app.services.aws_service import AWSService
from app.services.s3_service import S3Service
from app.services.user_config_service import UserConfigService
from app.services.document_service import DocumentService
from app.models.document import DocumentCreate
from app.models.user_config import CloudProvider

router = APIRouter()

@router.post("/upload-with-aws-analysis")
async def upload_document_with_aws_analysis(
    file: UploadFile = File(...),
    folder: Optional[str] = Form(None),
    user_token: dict = Depends(verify_token)
):
    """Subir documento y analizarlo con AWS Textract asíncrono y Comprehend"""
    try:
        # Verificar tipo de archivo
        if not file.filename:
            raise HTTPException(status_code=400, detail="Nombre de archivo requerido")
        
        # Verificar que el archivo sea compatible con Textract
        supported_types = ['pdf', 'jpg', 'jpeg', 'png', 'tiff', 'bmp']
        file_extension = file.filename.split('.')[-1].lower() if '.' in file.filename else ''
        
        if file_extension not in supported_types:
            raise HTTPException(
                status_code=400, 
                detail=f"Tipo de archivo no soportado. Tipos permitidos: {', '.join(supported_types)}"
            )
        
        # Obtener configuración del usuario
        config_service = UserConfigService()
        user_config = await config_service.get_or_create_user_config(user_token['uid'])
        
        # Leer contenido del archivo
        content = await file.read()
        
        # Crear archivo temporal
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_extension}") as temp_file:
            temp_file.write(content)
            temp_file_path = temp_file.name
        
        try:
            # Inicializar servicios
            aws_service = AWSService()
            document_service = DocumentService()
            
            # Procesar documento con AWS (Textract asíncrono + Comprehend)
            print(f"🔍 Procesando documento con AWS Textract asíncrono...")
            
            # Usar el nuevo método que implementa la estrategia completa
            document = await document_service.process_document_with_aws(
                user_id=user_token['uid'],
                file_data=content,
                file_name=file.filename,
                file_type=file.content_type
            )
            
            # Preparar metadatos del análisis para la respuesta
            analysis_metadata = {
                'ocr': {},
                'comprehend': {}
            }
            
            if document.ai_analysis:
                extraction = document.ai_analysis.get('extraction', {})
                comprehend = document.ai_analysis.get('comprehend', {})
                
                analysis_metadata['ocr'] = {
                    'extracted_text': document.extracted_text,
                    'text_length': len(document.extracted_text),
                    'method': extraction.get('method', 'unknown'),
                    'confidence': extraction.get('confidence', 0.0),
                    'blocks_count': extraction.get('blocks_count', 0),
                    'line_blocks_count': extraction.get('line_blocks_count', 0),
                    'word_blocks_count': extraction.get('word_blocks_count', 0),
                    'block_types': extraction.get('block_types', {}),
                    'raw_response': extraction.get('raw_response', {})
                }
                
                analysis_metadata['comprehend'] = {
                    'category': comprehend.get('category', 'General'),
                    'confidence': comprehend.get('confidence', 0.0),
                    'language': comprehend.get('language', 'unknown'),
                    'entities': comprehend.get('entities', []),
                    'key_phrases': comprehend.get('key_phrases', []),
                    'sentiments': comprehend.get('sentiments', []),
                    'chunks_processed': comprehend.get('chunks_processed', 0),
                    'text_length': comprehend.get('text_length', 0)
                }
            
            return {
                "message": "Documento procesado exitosamente con AWS Textract asíncrono",
                "document_id": document.id,
                "category": document.category,
                "file_url": document.file_url,
                "analysis": analysis_metadata
            }
            
        finally:
            # Limpiar archivo temporal
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
                
    except Exception as e:
        print(f"❌ Error procesando documento: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Error procesando documento: {str(e)}"
        )

@router.get("/s3/folders")
async def get_s3_folders(user_token: dict = Depends(verify_token)):
    """Obtener estructura de carpetas de S3"""
    try:
        s3_service = S3Service()
        folders = await s3_service.list_user_folders(user_token['uid'])
        documents = await s3_service.list_user_documents(user_token['uid'])
        
        return {
            "folders": folders,
            "documents": documents
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/s3/storage-usage")
async def get_storage_usage(user_token: dict = Depends(verify_token)):
    """Obtener información de uso de almacenamiento"""
    try:
        s3_service = S3Service()
        usage = await s3_service.get_storage_usage(user_token['uid'])
        return usage
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/create-user-folders")
async def create_user_folders(user_token: dict = Depends(verify_token)):
    """Crear estructura de carpetas del usuario en S3"""
    try:
        aws_service = AWSService()
        result = await aws_service.create_user_folders(user_token['uid'])
        return {
            "message": "Carpetas creadas exitosamente",
            "folders": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/create-category-folder")
async def create_category_folder(
    category: str = Form(...),
    user_token: dict = Depends(verify_token)
):
    """Crear carpeta de categoría específica en S3"""
    try:
        aws_service = AWSService()
        folder_path = await aws_service.create_category_folder(user_token['uid'], category)
        return {
            "message": f"Carpeta de categoría '{category}' creada exitosamente",
            "folder_path": folder_path
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))