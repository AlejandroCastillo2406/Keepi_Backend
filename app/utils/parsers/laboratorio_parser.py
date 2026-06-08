import json
import logging
from app.services.aws.bedrock_service import BedrockService

logger = logging.getLogger(__name__)

async def procesar_laboratorio(texto_raw: str):
    ai = BedrockService()
    
    prompt = f"""
    Eres un asistente médico experto en interpretar resultados de laboratorio.
    Extrae la información de este texto y devuélvela en un JSON estructurado.
    Si un campo no existe, pon null.
    
    TEXTO DEL LABORATORIO:
    {texto_raw[:3000]}
    
    Responde ÚNICAMENTE un JSON con:
    {{
        "estudio": "Nombre del estudio (ej. Hemoglobina)",
        "resultado": "El valor numérico o texto",
        "unidad": "Ej. mg/dL, g/L",
        "rango_referencia": "Lo que indica el laboratorio como normal",
        "interpretacion": "Normal, Alto, Bajo"
    }}
    (Si hay múltiples estudios, devuelve una lista de objetos bajo la clave "estudios")
    """
    
    try:
        respuesta = await ai._call_claude(prompt)
        # Limpiar markdown
        respuesta = respuesta.replace("```json", "").replace("```", "").strip()
        return json.loads(respuesta)
    except Exception as e:
        logger.error(f"Error parseando laboratorio: {e}")
        return {"error": "No se pudo extraer la información del laboratorio"}