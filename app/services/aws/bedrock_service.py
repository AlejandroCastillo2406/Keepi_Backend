import base64
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

    async def analyze_document_content(
        self, text: str, filename: str, existing_folder_names: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Analiza el contenido del documento usando Claude 3 Haiku.
        existing_folder_names: nombres de carpetas existentes del usuario; si el documento encaja en una, usarla.
        """
        if not self.bedrock_client:
            return {
                "category": "Sin categoría",
                "confidence": 0.0,
                "expiry_date": None,
                "recommended_name": None,
                "tags": [],
                "error": "Bedrock no disponible"
            }

        try:
            prompt = self._create_analysis_prompt(text, filename, existing_folder_names or [])
            
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
                "recommended_name": None,
                "tags": [],
                "error": str(e)
            }

    async def analyze_image_for_category(
        self,
        image_bytes: bytes,
        filename: str,
        media_type: str = "image/jpeg",
        existing_folder_names: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Analiza una imagen (foto/documento escaneado) con Claude 3 Haiku visión.
        Se usa cuando Textract no extrae texto suficiente (ej. foto de documento).
        Devuelve el mismo formato que analyze_document_content.
        """
        if not self.bedrock_client:
            return {
                "category": "MANUAL_CLASSIFICATION_REQUIRED",
                "confidence": 0.0,
                "expiry_date": None,
                "recommended_name": None,
                "tags": [],
                "error": "Bedrock no disponible",
            }
        try:
            prompt = self._create_image_analysis_prompt(filename, existing_folder_names or [])
            content = [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type if media_type.startswith("image/") else "image/jpeg",
                        "data": base64.b64encode(image_bytes).decode("utf-8"),
                    },
                },
                {"type": "text", "text": prompt},
            ]
            response_text = await self._call_claude_multimodal(content)
            result = self._parse_claude_response(response_text)
            category = result.get("category", "Sin categoría")
            if category in ("Sin categoría", "MANUAL_CLASSIFICATION_REQUIRED", ""):
                result["category"] = "MANUAL_CLASSIFICATION_REQUIRED"
            return result
        except Exception as e:
            logger.warning("Error analizando imagen con Bedrock (visión): %s", e)
            return {
                "category": "MANUAL_CLASSIFICATION_REQUIRED",
                "confidence": 0.0,
                "expiry_date": None,
                "recommended_name": None,
                "tags": [],
                "error": str(e),
            }

    def _create_image_analysis_prompt(self, filename: str, existing_folder_names: List[str]) -> str:
        """Prompt para que Claude analice la imagen y devuelva categoría y metadatos en JSON."""
        folders_instruction = ""
        if existing_folder_names:
            folders_list = ", ".join(f'"{n}"' for n in existing_folder_names[:50])
            folders_instruction = f"""
CARPETAS EXISTENTES DEL USUARIO: [{folders_list}]
- Si el documento en la imagen encaja en UNA de estas categorías, usa EXACTAMENTE ese nombre en "category".
- Si no encaja en ninguna, propón una NUEVA categoría amplia (máximo 3 palabras).
"""
        return f"""
Analiza la imagen adjunta (documento o foto de documento llamada "{filename}") y devuelve en UN solo JSON:

1. CATEGORÍA: Determina qué tipo de documento es (máximo 3 palabras, ASCII).
   - Ejemplos: "Documentos personales" (DNI, RFC, INE, pasaporte), "Facturas", "Contratos", "Recetas médicas", "Certificados", "Seguros", "Comprobantes fiscales", "Fotos personales", "Otros".
{folders_instruction}

2. FECHA DE VENCIMIENTO: Si ves una fecha de vencimiento/expiración en la imagen, formato YYYY-MM-DD. Si no, null.

3. CONFIANZA: Qué tan seguro estás de la categoría (0.0 a 1.0).

4. NOMBRE RECOMENDADO: Nombre sugerido para el archivo basado en el contenido visible. Respeta la extensión de "{filename}".

5. TAGS: Lista de 1 a 5 etiquetas en minúsculas.

Responde SOLO con este JSON válido (sin markdown ni texto extra):
{{
    "category": "nombre_categoria_amplia",
    "confidence": 0.95,
    "expiry_date": "2024-12-31" o null,
    "recommended_name": "nombre sugerido.ext",
    "tags": ["tag1", "tag2"]
}}
"""

    async def _call_claude_multimodal(self, content: list) -> str:
        """Invocar Claude con contenido multimodal (imagen + texto)."""
        try:
            body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 1000,
                "messages": [{"role": "user", "content": content}],
            }
            response = self.bedrock_client.invoke_model(
                modelId=self.model_id,
                body=json.dumps(body),
                contentType="application/json",
            )
            response_body = json.loads(response["body"].read())
            return response_body["content"][0]["text"]
        except (ClientError, Exception) as e:
            logger.warning("Error llamando a Claude (multimodal): %s", e)
            raise

    def _create_analysis_prompt(
        self, text: str, filename: str, existing_folder_names: List[str]
    ) -> str:
        """Crea el prompt para Claude 3 Haiku (una sola llamada con todo)."""
        folders_instruction = ""
        if existing_folder_names:
            folders_list = ", ".join(f'"{n}"' for n in existing_folder_names[:50])
            folders_instruction = f"""
CARPETAS EXISTENTES DEL USUARIO: [{folders_list}]
- Si el documento encaja claramente en UNA de estas categorías, usa EXACTAMENTE ese nombre en "category".
- Si no encaja en ninguna, propón una NUEVA categoría amplia (máximo 3 palabras).
"""

        return f"""
Analiza el siguiente texto extraído de un documento llamado "{filename}" y devuelve en UN solo JSON:

1. CATEGORÍA: Usa categorías AMPLIAS que agrupen varios tipos de documento (máximo 3 palabras, ASCII).
   - Ejemplos de categorías amplias: "Documentos personales" (para DNI, RFC, CURP, INE, pasaporte, cédula), "Facturas", "Contratos", "Recetas médicas", "Certificados académicos", "Seguros", "Comprobantes fiscales".
   - NO uses categorías muy específicas como "DNI" o "INE"
{folders_instruction}

2. FECHA DE VENCIMIENTO: Si hay fecha de vencimiento/expiración, en formato YYYY-MM-DD. Si no hay, null. Es importante NO confundir la fecha de expedicion con la fecha de vencimiento..

3. CONFIANZA: Qué tan seguro estás de la categoría (0.0 a 1.0).

4. NOMBRE RECOMENDADO DEL ARCHIVO: Debe ser MUY ESPECÍFICO. Extrae del texto el dato principal que identifica el documento y úsalo en el nombre. Formato: "[Tipo documento] [Dato identificador].ext".
   - Documentos personales (RFC, CURP, INE, pasaporte): usa el NOMBRE COMPLETO del titular. Ejemplo: "RFC Cesar Alejandro Castillo Garces.pdf", "INE Maria Lopez Hernandez.pdf".
   - Facturas/comprobantes: razón social o nombre del proveedor + folio o fecha. Ejemplo: "Factura CFE 2024-01.pdf".
   - Contratos: partes o objeto + fecha. Ejemplo: "Contrato arrendamiento 2024-03.pdf".
   - Sin guiones bajos; usa espacios. Respeta la extensión del archivo original.

5. TAGS: Lista de 1 a 5 etiquetas en minúsculas. Sin duplicar la categoría.

Responde SOLO con este JSON válido (sin markdown ni texto extra):
{{
    "category": "nombre_categoria_amplia",
    "confidence": 0.95,
    "expiry_date": "2024-12-31" o null,
    "recommended_name": "RFC Cesar Alejandro Castillo Garces.pdf",
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
            
            recommended_name = result.get('recommended_name')
            if recommended_name is not None and isinstance(recommended_name, str) and recommended_name.strip():
                recommended_name = recommended_name.strip()
            else:
                recommended_name = None
            tags = result.get('tags')
            if not isinstance(tags, list):
                tags = []
            tags = [str(t).strip().lower() for t in tags if t and str(t).strip()][:10]

            return {
                "category": category,
                "confidence": confidence,
                "expiry_date": expiry_date,
                "recommended_name": recommended_name,
                "tags": tags,
                "error": None
            }

        except json.JSONDecodeError as e:
            logger.error(f"Error parseando respuesta de Claude: {e}")
            return {
                "category": "Sin categoría",
                "confidence": 0.0,
                "expiry_date": None,
                "recommended_name": None,
                "tags": [],
                "error": "Error parseando respuesta de Claude"
            }
        except Exception as e:
            logger.error(f"Error procesando respuesta de Claude: {e}")
            return {
                "category": "Sin categoría",
                "confidence": 0.0,
                "expiry_date": None,
                "recommended_name": None,
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
