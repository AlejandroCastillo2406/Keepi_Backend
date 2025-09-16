import json
import re
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import boto3
from botocore.exceptions import ClientError
import logging

logger = logging.getLogger(__name__)

class BedrockService:
    def __init__(self):
        """Inicializa el servicio de Amazon Bedrock"""
        try:
            self.bedrock_client = boto3.client(
                'bedrock-runtime',
                region_name='us-east-1'  # Cambiar según tu región
            )
            self.model_id = "anthropic.claude-3-haiku-20240307-v1:0"
        except Exception as e:
            logger.error(f"Error inicializando Bedrock: {e}")
            self.bedrock_client = None

    async def analyze_document_content(self, text: str, filename: str) -> Dict[str, Any]:
        """
        Analiza el contenido del documento usando Claude 3 Haiku
        """
        if not self.bedrock_client:
            return {
                "category": "Sin categoría",
                "confidence": 0.0,
                "expiry_date": None,
                "error": "Bedrock no disponible"
            }

        try:
            # Crear prompt para Claude
            prompt = self._create_analysis_prompt(text, filename)
            
            # Llamar a Claude
            response = await self._call_claude(prompt)
            
            # Parsear respuesta
            result = self._parse_claude_response(response)
            
            return result
            
        except Exception as e:
            logger.error(f"Error analizando documento con Bedrock: {e}")
            return {
                "category": "Sin categoría",
                "confidence": 0.0,
                "expiry_date": None,
                "error": str(e)
            }

    def _create_analysis_prompt(self, text: str, filename: str) -> str:
        """Crea el prompt para Claude 3 Haiku"""
        return f"""
Analiza el siguiente texto extraído de un documento llamado "{filename}" y determina:

1. CATEGORÍA: Clasifica el documento en una categoría apropiada basándote en su contenido. 
   - NO uses categorías predefinidas
   - Determina la categoría más apropiada según el contexto del documento
   - Usa un nombre descriptivo pero conciso (máximo 3 palabras)
   - Ejemplos de categorías que podrías usar: "Certificado Académico", "Contrato Laboral", "Factura", "Receta Médica", "DNI", "Seguro Vehículo", etc.

2. FECHA DE VENCIMIENTO: Si encuentras alguna fecha que parezca ser de vencimiento, expírala en formato YYYY-MM-DD. Si no hay fecha de vencimiento, responde "null".

3. CONFIANZA: Evalúa qué tan seguro estás de la categorización (0.0 a 1.0).

Responde SOLO en formato JSON válido:
{{
    "category": "nombre_de_la_categoria_dinamica",
    "confidence": 0.95,
    "expiry_date": "2024-12-31" o null
}}

TEXTO DEL DOCUMENTO:
{text[:4000]}  # Limitar a 4000 caracteres para evitar límites de tokens
"""

    async def _call_claude(self, prompt: str) -> str:
        """Llama a Claude 3 Haiku a través de Bedrock"""
        try:
            body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 1000,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            }

            response = self.bedrock_client.invoke_model(
                modelId=self.model_id,
                body=json.dumps(body),
                contentType="application/json"
            )

            response_body = json.loads(response['body'].read())
            return response_body['content'][0]['text']
            
        except ClientError as e:
            logger.error(f"Error llamando a Claude: {e}")
            raise
        except Exception as e:
            logger.error(f"Error inesperado en Bedrock: {e}")
            raise

    def _parse_claude_response(self, response: str) -> Dict[str, Any]:
        """Parsea la respuesta de Claude"""
        try:
            # Limpiar la respuesta para extraer solo el JSON
            response = response.strip()
            if response.startswith('```json'):
                response = response[7:]
            if response.endswith('```'):
                response = response[:-3]
            
            # Parsear JSON
            result = json.loads(response)
            
            # Validar y limpiar resultado
            category = result.get('category', 'Sin categoría')
            confidence = float(result.get('confidence', 0.0))
            expiry_date = result.get('expiry_date')
            
            # Validar fecha de vencimiento
            if expiry_date and expiry_date != "null":
                try:
                    # Validar formato de fecha
                    datetime.strptime(expiry_date, '%Y-%m-%d')
                except ValueError:
                    expiry_date = None
            else:
                expiry_date = None
            
            return {
                "category": category,
                "confidence": confidence,
                "expiry_date": expiry_date,
                "error": None
            }
            
        except json.JSONDecodeError as e:
            logger.error(f"Error parseando respuesta de Claude: {e}")
            return {
                "category": "Sin categoría",
                "confidence": 0.0,
                "expiry_date": None,
                "error": "Error parseando respuesta de Claude"
            }
        except Exception as e:
            logger.error(f"Error procesando respuesta de Claude: {e}")
            return {
                "category": "Sin categoría",
                "confidence": 0.0,
                "expiry_date": None,
                "error": str(e)
            }

    def extract_dates_from_text(self, text: str) -> List[str]:
        """Extrae fechas del texto usando expresiones regulares"""
        date_patterns = [
            r'\b\d{1,2}[/-]\d{1,2}[/-]\d{4}\b',  # DD/MM/YYYY o DD-MM-YYYY
            r'\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b',  # YYYY/MM/DD o YYYY-MM-DD
            r'\b\d{1,2}\s+de\s+\w+\s+de\s+\d{4}\b',  # DD de MES de YYYY
            r'\b\w+\s+\d{1,2},?\s+\d{4}\b',  # MES DD, YYYY
        ]
        
        dates = []
        for pattern in date_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            dates.extend(matches)
        
        return dates

    def is_expiry_date(self, date_str: str, context: str) -> bool:
        """Determina si una fecha es probablemente de vencimiento"""
        expiry_keywords = [
            'vencimiento', 'expira', 'válido hasta', 'caduca',
            'expiry', 'expires', 'valid until', 'expires on'
        ]
        
        context_lower = context.lower()
        for keyword in expiry_keywords:
            if keyword in context_lower:
                return True
        
        return False
