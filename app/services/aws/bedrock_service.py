import base64
import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class BedrockService:
    def __init__(self):
        try:
            self.bedrock_client = boto3.client(
                "bedrock-runtime", region_name="us-east-1"
            )
            self.model_id = "anthropic.claude-3-haiku-20240307-v1:0"
        except Exception as e:
            logger.error(f"Error inicializando Bedrock: {e}")
            self.bedrock_client = None

    async def detectar_tipo_documento(self, texto: str) -> str:
        """
        Clasifica el documento para saber quÃ© parser usar.
        Retorna: "RECETA", "LABORATORIO", "IDENTIFICACION" o "OTRO".
        """
        if not self.bedrock_client:
            return "OTRO"
        
        prompt = f"""
        Analiza el siguiente texto extraÃ­do de un documento mÃ©dico o administrativo.
        ClasifÃ­calo estrictamente en UNA de estas categorÃ­as: "RECETA", "LABORATORIO", "IDENTIFICACION", "OTRO".
        
        Reglas:
        - Si ves medicamentos, indicaciones de dosis o folios de receta -> RECETA.
        - Si ves valores, unidades de medida, estudios clÃ­nicos o diagnÃ³sticos -> LABORATORIO.
        - Si ves datos personales (CURP, INE, RFC, PASAPORTE) -> IDENTIFICACION.
        - Si no encaja en ninguna -> OTRO.
        
        Responde ÃšNICAMENTE la palabra de la categorÃ­a, sin explicaciones ni formato adicional.
        
        TEXTO:
        {texto[:1500]}
        """
        try:
            respuesta = await self._call_claude(prompt)
            # Limpiamos posibles comillas o espacios extra
            return respuesta.strip().replace('"', '').upper()
        except Exception as e:
            logger.error(f"Error clasificando documento: {e}")
            return "OTRO"

    async def analyze_document_content(
        self,
        text: str,
        filename: str,
        existing_folder_names: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        if not self.bedrock_client:
            return {
                "category": "Sin categorÃ­a",
                "confidence": 0.0,
                "expiry_date": None,
                "recommended_name": None,
                "tags": [],
                "error": "Bedrock no disponible",
            }

        try:
            prompt = self._create_analysis_prompt(
                text, filename, existing_folder_names or []
            )

            response = await self._call_claude(prompt)

            result = self._parse_claude_response(response)

            return result

        except Exception as e:
            logger.error(f"Error analizando documento con Bedrock: {e}")
            return {
                "category": "Sin categorÃ­a",
                "confidence": 0.0,
                "expiry_date": None,
                "recommended_name": None,
                "tags": [],
                "error": str(e),
            }

    async def analyze_image_for_category(
        self,
        image_bytes: bytes,
        filename: str,
        media_type: str = "image/jpeg",
        existing_folder_names: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
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
            prompt = self._create_image_analysis_prompt(
                filename, existing_folder_names or []
            )
            content = [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": (
                            media_type
                            if media_type.startswith("image/")
                            else "image/jpeg"
                        ),
                        "data": base64.b64encode(image_bytes).decode("utf-8"),
                    },
                },
                {"type": "text", "text": prompt},
            ]
            response_text = await self._call_claude_multimodal(content)
            result = self._parse_claude_response(response_text)
            category = result.get("category", "Sin categorÃ­a")
            if category in ("Sin categorÃ­a", "MANUAL_CLASSIFICATION_REQUIRED", ""):
                result["category"] = "MANUAL_CLASSIFICATION_REQUIRED"
            return result
        except Exception as e:
            logger.warning("Error analizando imagen con Bedrock (visiÃ³n): %s", e)
            return {
                "category": "MANUAL_CLASSIFICATION_REQUIRED",
                "confidence": 0.0,
                "expiry_date": None,
                "recommended_name": None,
                "tags": [],
                "error": str(e),
            }

    def _create_image_analysis_prompt(
        self, filename: str, existing_folder_names: List[str]
    ) -> str:
        folders_instruction = ""
        if existing_folder_names:
            folders_list = ", ".join(f'"{n}"' for n in existing_folder_names[:50])
            folders_instruction = f"""
CARPETAS EXISTENTES DEL USUARIO: [{folders_list}]
- Si el documento en la imagen encaja en UNA de estas categorÃ­as, usa EXACTAMENTE ese nombre en "category".
- Si no encaja en ninguna, propÃ³n una NUEVA categorÃ­a amplia (mÃ¡ximo 3 palabras).
"""
        return f"""
Analiza la imagen adjunta (documento o foto de documento llamada "{filename}") y devuelve en UN solo JSON:

1. CATEGORÃA: Determina quÃ© tipo de documento es (mÃ¡ximo 3 palabras, ASCII).
   - Ejemplos: "Documentos personales" (DNI, RFC, INE, pasaporte), "Facturas", "Contratos", "Recetas mÃ©dicas", "Certificados", "Seguros", "Comprobantes fiscales", "Fotos personales", "Otros".
{folders_instruction}

2. FECHA DE VENCIMIENTO: Si ves una fecha de vencimiento/expiraciÃ³n en la imagen, formato YYYY-MM-DD. Si no, null.

3. CONFIANZA: QuÃ© tan seguro estÃ¡s de la categorÃ­a (0.0 a 1.0).

4. NOMBRE RECOMENDADO: Nombre sugerido para el archivo. OBLIGATORIO: usa la MISMA extensiÃ³n que "{filename}" (si es .jpg/.png/.jpeg NUNCA pongas .pdf si no es .PDF la original).

5. TAGS: Lista de 1 a 5 etiquetas en minÃºsculas.

Responde SOLO con este JSON vÃ¡lido (sin markdown ni texto extra):
{{
    "category": "nombre_categoria_amplia",
    "confidence": 0.95,
    "expiry_date": "2024-12-31" o null,
    "recommended_name": "nombre sugerido.ext",
    "tags": ["tag1", "tag2"]
}}
"""

    async def _call_claude_multimodal(self, content: list) -> str:
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
        folders_instruction = ""
        if existing_folder_names:
            folders_list = ", ".join(f'"{n}"' for n in existing_folder_names[:50])
            folders_instruction = f"""
CARPETAS EXISTENTES DEL USUARIO: [{folders_list}]
- Si el documento encaja claramente en UNA de estas categorÃ­as, usa EXACTAMENTE ese nombre en "category".
- Si no encaja en ninguna, propÃ³n una NUEVA categorÃ­a amplia (mÃ¡ximo 3 palabras).
"""

        return f"""
Analiza el siguiente texto extraÃ­do de un documento llamado "{filename}" y devuelve en UN solo JSON:

1. CATEGORÃA: Usa categorÃ­as AMPLIAS que agrupen varios tipos de documento (mÃ¡ximo 3 palabras, ASCII).
   - Ejemplos de categorÃ­as amplias: "Documentos personales" (para DNI, RFC, CURP, INE, pasaporte, cÃ©dula), "Facturas", "Contratos", "Recetas mÃ©dicas", "Certificados acadÃ©micos", "Seguros", "Comprobantes fiscales".
   - NO uses categorÃ­as muy especÃ­ficas como "DNI" o "INE"
{folders_instruction}

2. FECHA DE VENCIMIENTO: Si hay fecha de vencimiento/expiraciÃ³n, en formato YYYY-MM-DD. Si no hay, null. Es importante NO confundir la fecha de expedicion con la fecha de vencimiento..

3. CONFIANZA: QuÃ© tan seguro estÃ¡s de la categorÃ­a (0.0 a 1.0) TIENES QUE SER SINCERO Y NO PONER VALORES ALTOS SOLO POR PONER ALGO.

4. NOMBRE RECOMENDADO DEL ARCHIVO: Debe ser MUY ESPECÃFICO. Extrae del texto el dato principal que identifica el documento y Ãºsalo en el nombre. Formato: "[Tipo documento] [Dato identificador].ext".
   - Documentos personales (RFC, CURP, INE, pasaporte): usa el NOMBRE COMPLETO del titular. Ejemplo: "RFC Cesar Alejandro Castillo Garces.pdf", "INE Maria Lopez Hernandez.pdf".
   - Facturas/comprobantes: razÃ³n social o nombre del proveedor + folio o fecha. Ejemplo: "Factura CFE 2024-01.pdf".
   - Contratos: partes o objeto + fecha. Ejemplo: "Contrato arrendamiento 2024-03.pdf".
   - Sin guiones bajos; usa espacios. Respeta SIEMPRE la extensiÃ³n del archivo original (imagen = .jpg/.png/.jpeg, PDF = .pdf).

5. TAGS: Lista de 1 a 5 etiquetas en minÃºsculas. Sin duplicar la categorÃ­a.

Responde SOLO con este JSON vÃ¡lido (sin markdown ni texto extra):
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
        try:
            body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 1000,
                "messages": [{"role": "user", "content": prompt}],
            }

            response = self.bedrock_client.invoke_model(
                modelId=self.model_id,
                body=json.dumps(body),
                contentType="application/json",
            )

            response_body = json.loads(response["body"].read())
            return response_body["content"][0]["text"]

        except ClientError as e:
            logger.error(f"Error llamando a Claude: {e}")
            raise
        except Exception as e:
            logger.error(f"Error inesperado en Bedrock: {e}")
            raise

    def _parse_claude_response(self, response: str) -> Dict[str, Any]:
        try:

            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.endswith("```"):
                response = response[:-3]

            result = json.loads(response)

            category = result.get("category", "Sin categorÃ­a")
            confidence = float(result.get("confidence", 0.0))
            expiry_date = result.get("expiry_date")

            if expiry_date and expiry_date != "null":
                try:

                    if "T" in expiry_date:

                        date_part = expiry_date.split("T")[0]
                        parsed_date = datetime.strptime(date_part, "%Y-%m-%d")
                        expiry_date = parsed_date.strftime("%Y-%m-%dT00:00:00Z")
                    else:

                        parsed_date = datetime.strptime(expiry_date, "%Y-%m-%d")
                        expiry_date = parsed_date.strftime("%Y-%m-%dT00:00:00Z")
                except ValueError:
                    expiry_date = None
            else:
                expiry_date = None

            recommended_name = result.get("recommended_name")
            if (
                recommended_name is not None
                and isinstance(recommended_name, str)
                and recommended_name.strip()
            ):
                recommended_name = recommended_name.strip()
            else:
                recommended_name = None
            tags = result.get("tags")
            if not isinstance(tags, list):
                tags = []
            tags = [str(t).strip().lower() for t in tags if t and str(t).strip()][:10]

            return {
                "category": category,
                "confidence": confidence,
                "expiry_date": expiry_date,
                "recommended_name": recommended_name,
                "tags": tags,
                "error": None,
            }

        except json.JSONDecodeError as e:
            logger.error(f"Error parseando respuesta de Claude: {e}")
            return {
                "category": "Sin categorÃ­a",
                "confidence": 0.0,
                "expiry_date": None,
                "recommended_name": None,
                "tags": [],
                "error": "Error parseando respuesta de Claude",
            }
        except Exception as e:
            logger.error(f"Error procesando respuesta de Claude: {e}")
            return {
                "category": "Sin categorÃ­a",
                "confidence": 0.0,
                "expiry_date": None,
                "recommended_name": None,
                "tags": [],
                "error": str(e),
            }

    def extract_dates_from_text(self, text: str) -> List[str]:
        date_patterns = [
            r"\b\d{1,2}[/-]\d{1,2}[/-]\d{4}\b",
            r"\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b",
            r"\b\d{1,2}\s+de\s+\w+\s+de\s+\d{4}\b",
            r"\b\w+\s+\d{1,2},?\s+\d{4}\b",
        ]

        dates = []
        for pattern in date_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            dates.extend(matches)

        return dates

    def is_expiry_date(self, date_str: str, context: str) -> bool:
        expiry_keywords = [
            "vencimiento",
            "expira",
            "vÃ¡lido hasta",
            "caduca",
            "expiry",
            "expires",
            "valid until",
            "expires on",
        ]

        context_lower = context.lower()
        for keyword in expiry_keywords:
            if keyword in context_lower:
                return True

        return False

    async def clean_medical_questions(self, raw_text: str) -> List[Dict[str, Any]]:
        """
        Recibe el texto bruto extraÃ­do por OCR y le pide a Claude que estructure las preguntas 
        respetando FIELMENTE el texto original, sin inventar, y asignando el tipo de respuesta.
        """
        if not self.bedrock_client:
            logger.warning("Bedrock no disponible para limpiar preguntas.")
            return [{"texto": line, "tipo": "short_text", "opciones": None} for line in raw_text.split('\n') if len(line.strip()) > 8]

        prompt = f"""
        Eres un transcriptor estricto de documentos. A continuaciÃ³n recibes un texto extraÃ­do por OCR de una hoja escrita a mano por un doctor.
        
        REGLAS ESTRICTAS QUE DEBES OBEDECER SIN EXCEPCIÃ“N:
        1. FIDELIDAD ABSOLUTA: MantÃ©n las palabras EXACTAS que escribiÃ³ el doctor. NO reescribas la pregunta para que suene "mÃ¡s profesional", NO agregues palabras. Solo corrige errores de dedo ortogrÃ¡ficos obvios (ej. si dice "ciruyia" pon "cirugÃ­a", si dice "haz" pon "has") y asegÃºrate de abrir y cerrar con signos de interrogaciÃ³n ('Â¿' y '?').
        2. CERO ALUCINACIONES: Si hay texto basura, garabatos, manchas o letras sueltas al final (ej. "O M", "w6", nÃºmeros aleatorios), IGNÃ“RALOS por completo. NO inventes preguntas que no estÃ©n claramente escritas en el texto.
        3. DIVIDIR PREGUNTAS MÃšLTIPLES: Si una misma oraciÃ³n pide DOS datos numÃ©ricos o medidas distintas (por ejemplo: "Â¿CuÃ¡l es su peso y estatura?"), DIVÃDELA obligatoriamente en dos preguntas separadas (ej. "Â¿CuÃ¡l es su peso?" y "Â¿CuÃ¡l es su estatura?").
        4. CLASIFICAR EL TIPO DE RESPUESTA. Tus Ãºnicas opciones son:
            - "single_choice": Tiene opciones explÃ­citas y se elige una.
            - "multi_choice": Tiene opciones explÃ­citas y se eligen varias.
            - "yes_no": Pregunta de SÃ­ o No.
            - "numeric": Pregunta de peso, estatura, edad, cantidad, etc.
            - "short_text": Respuestas cortas o nombres.
            - "long_text": Explicaciones detalladas.
        5. Extraer las OPCIONES si el tipo es single_choice o multi_choice (sino, pon null).
        
        Devuelve ÃšNICAMENTE un objeto JSON vÃ¡lido con la siguiente estructura, sin texto extra ni markdown:
        {{
            "preguntas": [
                {{
                    "texto": "Â¿Conoces algÃºn medicamento?",
                    "tipo": "yes_no",
                    "opciones": null
                }},
                {{
                    "texto": "Â¿Te has hecho una cirugÃ­a?",
                    "tipo": "yes_no",
                    "opciones": null
                }}
            ]
        }}
        
        Texto extraÃ­do por OCR:
        {raw_text[:2000]}
        """

        try:
            response_text = await self._call_claude(prompt)
            
            response_text = response_text.strip()
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]

            result = json.loads(response_text)
            return result.get("preguntas", [])
            
        except Exception as e:
            logger.error(f"Error en IA al limpiar preguntas: {e}")
            return [{"texto": line, "tipo": "short_text", "opciones": None} for line in raw_text.split('\n') if len(line.strip()) > 8]
