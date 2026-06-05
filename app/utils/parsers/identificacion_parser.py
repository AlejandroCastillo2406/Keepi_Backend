import json
import logging
from app.services.aws.bedrock_service import BedrockService

logger = logging.getLogger(__name__)

async def procesar_identificacion(texto_raw: str):
    ai = BedrockService()
    
    prompt = f"""
    Eres un asistente administrativo. Extrae los datos de esta identificación.
    
    TEXTO DEL DOCUMENTO:
    {texto_raw[:2000]}
    
    Responde ÚNICAMENTE un JSON con:
    {{
        "nombre_completo": "...",
        "numero_id": "CURP, INE o numero de pasaporte",
        "fecha_nacimiento": "YYYY-MM-DD",
        "fecha_vencimiento": "YYYY-MM-DD o null",
        "tipo_identificacion": "INE, Pasaporte, Licencia"
    }}
    """
    
    try:
        respuesta = await ai._call_claude(prompt)
        respuesta = respuesta.replace("```json", "").replace("```", "").strip()
        return json.loads(respuesta)
    except Exception as e:
        logger.error(f"Error parseando identificación: {e}")
        return {"error": "No se pudo extraer la identificación"}