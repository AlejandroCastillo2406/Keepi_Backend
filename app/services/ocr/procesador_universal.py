from typing import Any, Dict
from app.services.ocr.ocr_service import OCRService
from app.services.aws.bedrock_service import BedrockService
# Importamos los especialistas
from app.utils.parsers.prescription_cedula_parser import procesar_receta_con_seguridad # Asumiendo que moviste tu lógica aquí
from app.utils.parsers.laboratorio_parser import procesar_laboratorio
from app.utils.parsers.identificacion_parser import procesar_identificacion

class ProcesadorUniversal:
    def __init__(self):
        self.ocr = OCRService()
        self.ai = BedrockService()

    async def procesar(self, file_path: str, file_type: str, filename: str) -> Dict[str, Any]:
        # 1. OCR Universal
        ocr_data = await self.ocr.extract_text_from_document(file_path, file_type)
        texto_raw = ocr_data["full_text"]
        
        # 2. Clasificación Inteligente
        tipo_documento = await self.ai.detectar_tipo_documento(texto_raw)
        
        # 3. Enrutamiento (Dispatcher)
        datos_extraidos = {}
        
        if tipo_documento == "RECETA":
            datos_extraidos = procesar_receta_con_seguridad(texto_raw, mantener_detalle_completo=True)
            
        elif tipo_documento == "LABORATORIO":
            datos_extraidos = await procesar_laboratorio(texto_raw)
            
        elif tipo_documento == "IDENTIFICACION":
            datos_extraidos = await procesar_identificacion(texto_raw)
            
        else:
            datos_extraidos = {"mensaje": "Documento genérico"}
            
        return {
            "tipo_detectado": tipo_documento,
            "datos_extraidos": datos_extraidos,
            "metadatos_ocr": ocr_data
        }