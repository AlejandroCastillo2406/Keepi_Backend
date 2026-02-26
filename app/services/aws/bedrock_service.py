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
                "document_number": None,
                "organization": None,
                "tags": [],
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
                "document_number": None,
                "organization": None,
                "tags": [],
                "error": str(e)
            }

    def _create_analysis_prompt(self, text: str, filename: str) -> str:
        """Crea el prompt para Claude 3 Haiku (una sola llamada con todo)."""
        return f"""
Analiza el siguiente texto extraído de un documento llamado "{filename}" y devuelve en UN solo JSON:

1. CATEGORÍA: Clasifica el documento (máximo 3 palabras, ASCII). Ejemplos: "Certificado Académico", "Contrato Laboral", "Factura", "Receta Médica", "DNI", "Seguro Vehículo".

2. FECHA DE VENCIMIENTO: Si hay fecha de vencimiento/expiración/validez, en formato YYYY-MM-DD. Si no hay, null.

3. CONFIANZA: Qué tan seguro estás de la categoría (0.0 a 1.0).

4. NÚMERO DE DOCUMENTO: Folio, código, número de contrato o identificador principal si aparece. Si no, null.

5. ORGANIZACIÓN: Empresa, institución, banco o entidad que emite el documento si aparece. Si no, null.

6. TAGS: Lista de 1 a 5 etiquetas en minúsculas (ej: ["factura", "tributario"], ["identificación"], ["académico"]). Sin duplicar la categoría.

Responde SOLO con este JSON válido (sin markdown ni texto extra):
{{
    "category": "nombre_categoria",
    "confidence": 0.95,
    "expiry_date": "2024-12-31" o null,
    "document_number": "XXX-123" o null,
    "organization": "Nombre entidad" o null,
    "tags": ["tag1", "tag2"]
}}

TEXTO DEL DOCUMENTO:
{text[:4000]}
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
                    # Si ya viene con tiempo, normalizar a formato Z
                    if 'T' in expiry_date:
                        # Evitar duplicados de sufijo. Tomar solo fecha y forzar 00:00:00Z
                        date_part = expiry_date.split('T')[0]
                        parsed_date = datetime.strptime(date_part, '%Y-%m-%d')
                        expiry_date = parsed_date.strftime('%Y-%m-%dT00:00:00Z')
                    else:
                        # Convertir YYYY-MM-DD -> YYYY-MM-DDT00:00:00Z
                        parsed_date = datetime.strptime(expiry_date, '%Y-%m-%d')
                        expiry_date = parsed_date.strftime('%Y-%m-%dT00:00:00Z')
                except ValueError:
                    expiry_date = None
            else:
                expiry_date = None
            
            document_number = result.get('document_number')
            if document_number is not None and (not isinstance(document_number, str) or document_number.strip() in ('', 'null')):
                document_number = None
            organization = result.get('organization')
            if organization is not None and (not isinstance(organization, str) or organization.strip() in ('', 'null')):
                organization = None
            tags = result.get('tags')
            if not isinstance(tags, list):
                tags = []
            tags = [str(t).strip().lower() for t in tags if t and str(t).strip()][:10]

            return {
                "category": category,
                "confidence": confidence,
                "expiry_date": expiry_date,
                "document_number": document_number,
                "organization": organization,
                "tags": tags,
                "error": None
            }

        except json.JSONDecodeError as e:
            logger.error(f"Error parseando respuesta de Claude: {e}")
            return {
                "category": "Sin categoría",
                "confidence": 0.0,
                "expiry_date": None,
                "document_number": None,
                "organization": None,
                "tags": [],
                "error": "Error parseando respuesta de Claude"
            }
        except Exception as e:
            logger.error(f"Error procesando respuesta de Claude: {e}")
            return {
                "category": "Sin categoría",
                "confidence": 0.0,
                "expiry_date": None,
                "document_number": None,
                "organization": None,
                "tags": [],
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
