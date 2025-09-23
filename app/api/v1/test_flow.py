from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from typing import List, Optional, Dict, Any
import tempfile
import os
from datetime import datetime

from app.utils.auth import verify_token
from app.services.document_service import DocumentService
from app.services.user_config_service import UserConfigService
from app.services.oauth_service import GoogleOAuthService
from app.services.drive_service import GoogleDriveService

router = APIRouter()

@router.post("/complete-flow")
async def test_complete_flow(
    file: UploadFile = File(...),
    storage_preference: str = Form(..., description="keepi_cloud o google_drive"),
    user_token: dict = Depends(verify_token)
):
    """
    Flujo completo de prueba: autenticación, selección de almacenamiento, 
    análisis con Bedrock y creación de carpetas
    """
    try:
        print(f"🚀 Iniciando flujo completo para usuario: {user_token['uid']}")
        print(f"📁 Archivo: {file.filename}")
        print(f"💾 Almacenamiento: {storage_preference}")
        
        # PASO 1: Verificar/Configurar preferencia de almacenamiento
        user_config_service = UserConfigService()
        user_config = await user_config_service.get_user_config(user_token['uid'])
        
        if not user_config:
            # Crear configuración inicial
            from app.models.user_config import UserConfigCreate, CloudProvider
            config_data = UserConfigCreate(
                cloud_provider=CloudProvider.KEEPI_CLOUD if storage_preference == "keepi_cloud" else CloudProvider.GOOGLE_DRIVE
            )
            await user_config_service.create_user_config(
                user_token['uid'],
                config_data
            )
            print(f"✅ Configuración creada: {storage_preference}")
        else:
            # Actualizar preferencia si es diferente
            if user_config.cloud_provider.value != storage_preference:
                from app.models.user_config import UserConfigUpdate, CloudProvider
                update_data = UserConfigUpdate(
                    cloud_provider=CloudProvider.KEEPI_CLOUD if storage_preference == "keepi_cloud" else CloudProvider.GOOGLE_DRIVE
                )
                await user_config_service.update_user_config(
                    user_token['uid'],
                    update_data
                )
                print(f"✅ Configuración actualizada: {storage_preference}")
            else:
                print(f"✅ Configuración existente: {storage_preference}")
        
        # PASO 2: Verificar autorización de Google Drive si es necesario
        drive_auth_url = None
        if storage_preference == "google_drive":
            oauth_service = GoogleOAuthService()
            auth_status = await oauth_service.check_user_drive_access(user_token['uid'])
            
            if auth_status['status'] != 'active':
                # Generar URL de autorización
                auth_url = await oauth_service.get_authorization_url(user_token['uid'])
                drive_auth_url = auth_url
                print(f"🔗 URL de autorización Drive: {auth_url}")
                
                return {
                    "success": False,
                    "requires_drive_auth": True,
                    "drive_auth_url": auth_url,
                    "message": "Se requiere autorización de Google Drive. Usa la URL proporcionada para autorizar."
                }
            else:
                print("✅ Autorización de Google Drive activa")
        
        # PASO 3: Procesar documento con Bedrock
        content = await file.read()
        document_service = DocumentService()
        
        print(f"🤖 Procesando documento con Bedrock...")
        document = await document_service.process_document_with_bedrock(
            user_token['uid'],
            content,
            file.filename,
            file.content_type or "application/octet-stream"
        )
        
        print(f"✅ Documento procesado:")
        print(f"   Categoría: {document.category}")
        print(f"   Confianza: {document.ai_analysis.get('confidence_score', 0) if document.ai_analysis else 0}")
        print(f"   Fecha de vencimiento: {document.expiry_date}")
        print(f"   URL del archivo: {document.file_url}")
        
        # PASO 4: Obtener información de la carpeta creada
        folder_info = {
            "storage_type": storage_preference,
            "folder_created": True,
            "folder_name": document.category,
            "file_url": document.file_url
        }
        
        if storage_preference == "keepi_cloud":
            folder_info["s3_key"] = document.s3_key
            folder_info["message"] = f"Carpeta '{document.category}' creada en S3"
        elif storage_preference == "google_drive":
            folder_info["drive_file_id"] = document.s3_key.split('/')[-1] if document.s3_key else None
            folder_info["message"] = f"Carpeta '{document.category}' creada en Google Drive"
        
        return {
            "success": True,
            "message": "Flujo completo ejecutado exitosamente",
            "document": {
                "id": document.id,
                "name": document.name,
                "category": document.category,
                "confidence": document.ai_analysis.get('confidence_score', 0) if document.ai_analysis else 0,
                "expiry_date": document.expiry_date,
                "file_url": document.file_url,
                "tags": document.tags
            },
            "folder_info": folder_info,
            "storage_preference": storage_preference,
            "processing_time": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error en flujo completo: {e}")
        # Verificar si es una excepción de autorización de Drive
        if "DriveAuthRequiredException" in str(type(e)) or "requires_drive_auth" in str(e):
            from app.exceptions import DriveAuthRequiredException
            if isinstance(e, DriveAuthRequiredException):
                return {
                    "success": False,
                    "requires_drive_auth": True,
                    "message": e.message,
                    "drive_auth_url": e.drive_auth_url,
                    "error": "Se requiere autorización de Google Drive"
                }
            else:
                return {
                    "success": False,
                    "requires_drive_auth": True,
                    "message": "Se requiere autorización de Google Drive",
                    "drive_auth_url": "https://accounts.google.com/oauth/authorize?client_id=YOUR_CLIENT_ID&redirect_uri=YOUR_REDIRECT_URI&scope=https://www.googleapis.com/auth/drive&response_type=code&access_type=offline",
                    "error": str(e)
                }
        else:
            raise HTTPException(status_code=500, detail=str(e))

@router.get("/test-files")
async def get_test_files_info():
    """
    Información sobre los archivos de prueba disponibles
    """
    return {
        "test_files": [
            {
                "name": "prueba.pdf",
                "type": "application/pdf",
                "description": "Documento PDF para probar OCR y análisis"
            },
            {
                "name": "prueba.jpeg",
                "type": "image/jpeg", 
                "description": "Imagen JPEG para probar OCR de imágenes"
            },
            {
                "name": "prueba.docx",
                "type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "description": "Documento Word para probar extracción de texto"
            }
        ],
        "instructions": "Sube cualquiera de estos archivos usando el endpoint /complete-flow"
    }

@router.get("/user-status")
async def get_user_status(user_token: dict = Depends(verify_token)):
    """
    Obtener estado actual del usuario y configuración
    """
    try:
        user_config_service = UserConfigService()
        user_config = await user_config_service.get_user_config(user_token['uid'])
        
        # Verificar estado de Google Drive si está configurado
        drive_status = None
        if user_config and user_config.storage_preference == "google_drive":
            oauth_service = GoogleOAuthService()
            drive_status = await oauth_service.check_user_drive_access(user_token['uid'])
        
        return {
            "user_id": user_token['uid'],
            "email": user_token.get('email', 'N/A'),
            "storage_preference": user_config.storage_preference if user_config else None,
            "drive_status": drive_status,
            "is_configured": user_config is not None
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
