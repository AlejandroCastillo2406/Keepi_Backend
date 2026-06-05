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
        Clasifica el documento para saber qué parser usar.
        Retorna: "RECETA", "LABORATORIO", "IDENTIFICACION" o "OTRO".
        """
        if not self.bedrock_client:
            return "OTRO"
        
        prompt = f"""
        Analiza el siguiente texto extraído de un documento médico o administrativo.
        Clasifícalo estrictamente en UNA de estas categorías: "RECETA", "LABORATORIO", "IDENTIFICACION", "OTRO".
        
        Reglas:
        - Si ves medicamentos, indicaciones de dosis o folios de receta -> RECETA.
        - Si ves valores, unidades de medida, estudios clínicos o diagnósticos -> LABORATORIO.
        - Si ves datos personales (CURP, INE, RFC, PASAPORTE) -> IDENTIFICACION.
        - Si no encaja en ninguna -> OTRO.
        
        Responde ÚNICAMENTE la palabra de la categoría, sin explicaciones ni formato adicional.
        
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
                "category": "Sin categoría",
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
                "category": "Sin categoría",
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

    def _create_image_analysis_prompt(
        self, filename: str, existing_folder_names: List[str]
    ) -> str:
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

4. NOMBRE RECOMENDADO: Nombre sugerido para el archivo. OBLIGATORIO: usa la MISMA extensión que "{filename}" (si es .jpg/.png/.jpeg NUNCA pongas .pdf si no es .PDF la original).

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

3. CONFIANZA: Qué tan seguro estás de la categoría (0.0 a 1.0) TIENES QUE SER SINCERO Y NO PONER VALORES ALTOS SOLO POR PONER ALGO.

4. NOMBRE RECOMENDADO DEL ARCHIVO: Debe ser MUY ESPECÍFICO. Extrae del texto el dato principal que identifica el documento y úsalo en el nombre. Formato: "[Tipo documento] [Dato identificador].ext".
   - Documentos personales (RFC, CURP, INE, pasaporte): usa el NOMBRE COMPLETO del titular. Ejemplo: "RFC Cesar Alejandro Castillo Garces.pdf", "INE Maria Lopez Hernandez.pdf".
   - Facturas/comprobantes: razón social o nombre del proveedor + folio o fecha. Ejemplo: "Factura CFE 2024-01.pdf".
   - Contratos: partes o objeto + fecha. Ejemplo: "Contrato arrendamiento 2024-03.pdf".
   - Sin guiones bajos; usa espacios. Respeta SIEMPRE la extensión del archivo original (imagen = .jpg/.png/.jpeg, PDF = .pdf).

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

            category = result.get("category", "Sin categoría")
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
                "category": "Sin categoría",
                "confidence": 0.0,
                "expiry_date": None,
                "recommended_name": None,
                "tags": [],
                "error": "Error parseando respuesta de Claude",
            }
        except Exception as e:
            logger.error(f"Error procesando respuesta de Claude: {e}")
            return {
                "category": "Sin categoría",
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
            "válido hasta",
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
        Recibe el texto bruto extraído por OCR y le pide a Claude que estructure las preguntas 
        respetando FIELMENTE el texto original, sin inventar, y asignando el tipo de respuesta.
        """
        if not self.bedrock_client:
            logger.warning("Bedrock no disponible para limpiar preguntas.")
            return [{"texto": line, "tipo": "short_text", "opciones": None} for line in raw_text.split('\n') if len(line.strip()) > 8]

        prompt = f"""
        Eres un transcriptor estricto de documentos. A continuación recibes un texto extraído por OCR de una hoja escrita a mano por un doctor.
        
        REGLAS ESTRICTAS QUE DEBES OBEDECER SIN EXCEPCIÓN:
        1. FIDELIDAD ABSOLUTA: Mantén las palabras EXACTAS que escribió el doctor. NO reescribas la pregunta para que suene "más profesional", NO agregues palabras. Solo corrige errores de dedo ortográficos obvios (ej. si dice "ciruyia" pon "cirugía", si dice "haz" pon "has") y asegúrate de abrir y cerrar con signos de interrogación ('¿' y '?').
        2. CERO ALUCINACIONES: Si hay texto basura, garabatos, manchas o letras sueltas al final (ej. "O M", "w6", números aleatorios), IGNÓRALOS por completo. NO inventes preguntas que no estén claramente escritas en el texto.
        3. DIVIDIR PREGUNTAS MÚLTIPLES: Si una misma oración pide DOS datos numéricos o medidas distintas (por ejemplo: "¿Cuál es su peso y estatura?"), DIVÍDELA obligatoriamente en dos preguntas separadas (ej. "¿Cuál es su peso?" y "¿Cuál es su estatura?").
        4. CLASIFICAR EL TIPO DE RESPUESTA. Tus únicas opciones son:
            - "single_choice": Tiene opciones explícitas y se elige una.
            - "multi_choice": Tiene opciones explícitas y se eligen varias.
            - "yes_no": Pregunta de Sí o No.
            - "numeric": Pregunta de peso, estatura, edad, cantidad, etc.
            - "short_text": Respuestas cortas o nombres.
            - "long_text": Explicaciones detalladas.
        5. Extraer las OPCIONES si el tipo es single_choice o multi_choice (sino, pon null).
        
        Devuelve ÚNICAMENTE un objeto JSON válido con la siguiente estructura, sin texto extra ni markdown:
        {{
            "preguntas": [
                {{
                    "texto": "¿Conoces algún medicamento?",
                    "tipo": "yes_no",
                    "opciones": null
                }},
                {{
                    "texto": "¿Te has hecho una cirugía?",
                    "tipo": "yes_no",
                    "opciones": null
                }}
            ]
        }}
        
        Texto extraído por OCR:
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

    async def generate_dynamic_questionnaire_question(
        self,
        *,
        patient_name: str,
        conversation: List[Dict[str, Any]],
        question_number: int,
        max_questions: int = 10,
    ) -> Dict[str, Any]:
        """Genera la siguiente pregunta de un cuestionario clínico adaptativo."""
        fallback = self._fallback_dynamic_question(question_number, conversation)

        if not self.bedrock_client:
            return fallback

        history_lines = []
        for idx, turn in enumerate(conversation, start=1):
            q = (turn.get("question_text") or "").strip()
            a = turn.get("answer")
            if isinstance(a, list):
                a_text = ", ".join(str(x) for x in a)
            else:
                a_text = str(a) if a is not None else ""
            history_lines.append(f"{idx}. P: {q}\n  R: {a_text}")

        history_block = (
            "\n".join(history_lines) if history_lines else "(sin respuestas previas)"
        )

        prompt = f"""
Eres un asistente clínico que elabora UN cuestionario de salud breve para un paciente.
Paciente: {patient_name}
Pregunta actual a generar: {question_number} de {max_questions} (máximo).

Historial de preguntas y respuestas:
{history_block}

REGLAS:
1. Genera UNA sola pregunta nueva en español, clara y empática, sin repetir temas ya cubiertos.
2. La pregunta debe ser relevante para atención médica general (síntomas, antecedentes, hábitos, medicación, alergias, etc.).
3. Elige el tipo de respuesta más adecuado entre: single_choice, multi_choice, yes_no, numeric, short_text, long_text.
4. Para yes_no usa opciones ["No", "No estoy seguro", "Sí"].
5. Para single_choice o multi_choice incluye entre 3 y 6 opciones concretas.
6. Para numeric incluye help_text indicando la unidad si aplica.
7. is_required debe ser true salvo que la pregunta sea claramente opcional.

Responde SOLO JSON válido (sin markdown):
{{
  "question_text": "¿...?",
  "response_type": "yes_no",
  "options": ["No", "No estoy seguro", "Sí"],
  "help_text": null,
  "is_required": true
}}
"""
        try:
            response_text = await self._call_claude(prompt)
            response_text = response_text.strip()
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.startswith("```"):
                response_text = response_text[3:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]
            parsed = json.loads(response_text)
            rt = (parsed.get("response_type") or "short_text").lower()
            if rt not in (
                "single_choice",
                "multi_choice",
                "yes_no",
                "numeric",
                "short_text",
                "long_text",
            ):
                rt = "short_text"
            options = parsed.get("options")
            if rt == "yes_no":
                options = ["No", "No estoy seguro", "Sí"]
            if rt in ("single_choice", "multi_choice") and not options:
                rt = "short_text"
                options = None
            if rt not in ("single_choice", "multi_choice", "yes_no"):
                options = None
            return {
                "question_text": (parsed.get("question_text") or fallback["question_text"]).strip(),
                "response_type": rt,
                "options": options,
                "help_text": parsed.get("help_text"),
                "is_required": bool(parsed.get("is_required", True)),
            }
        except Exception as e:
            logger.warning("Bedrock cuestionario dinámico: %s", e)
            return fallback

    def _fallback_dynamic_question(
        self, question_number: int, conversation: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        asked = {((t.get("question_text") or "").lower()[:40]) for t in conversation}
        bank = [
            {
                "question_text": "¿Cuál es el motivo principal de tu consulta hoy?",
                "response_type": "long_text",
                "options": None,
                "help_text": "Describe brevemente tus síntomas o inquietudes.",
                "is_required": True,
            },
            {
                "question_text": "¿Desde cuándo has tenido estos síntomas?",
                "response_type": "short_text",
                "options": None,
                "help_text": "Ejemplo: 3 días, 2 semanas.",
                "is_required": True,
            },
            {
                "question_text": "¿Tomas algún medicamento de forma habitual?",
                "response_type": "yes_no",
                "options": ["No", "No estoy seguro", "Sí"],
                "help_text": None,
                "is_required": True,
            },
            {
                "question_text": "¿Tienes alergias conocidas a medicamentos o alimentos?",
                "response_type": "yes_no",
                "options": ["No", "No estoy seguro", "Sí"],
                "help_text": None,
                "is_required": True,
            },
            {
                "question_text": "¿Cuál es tu peso aproximado en kilogramos?",
                "response_type": "numeric",
                "options": None,
                "help_text": "Solo el número en kg.",
                "is_required": False,
            },
            {
                "question_text": "¿Fumas o consumes alcohol con regularidad?",
                "response_type": "single_choice",
                "options": ["No", "Ocasionalmente", "Con frecuencia"],
                "help_text": None,
                "is_required": True,
            },
            {
                "question_text": "¿Has tenido cirugías previas?",
                "response_type": "yes_no",
                "options": ["No", "No estoy seguro", "Sí"],
                "help_text": None,
                "is_required": True,
            },
            {
                "question_text": "¿Algún familiar directo tiene enfermedades crónicas importantes?",
                "response_type": "multi_choice",
                "options": [
                    "Diabetes",
                    "Hipertensión",
                    "Cáncer",
                    "Ninguna",
                    "No lo sé",
                ],
                "help_text": "Puedes elegir varias.",
                "is_required": False,
            },
            {
                "question_text": "¿Cómo calificarías tu nivel de actividad física?",
                "response_type": "single_choice",
                "options": ["Sedentario", "Ligero", "Moderado", "Activo"],
                "help_text": None,
                "is_required": True,
            },
            {
                "question_text": "¿Hay algo más que quieras que tu médico sepa antes de la consulta?",
                "response_type": "long_text",
                "options": None,
                "help_text": "Opcional.",
                "is_required": False,
            },
        ]
        idx = min(question_number - 1, len(bank) - 1)
        for i in range(len(bank)):
            candidate = bank[(idx + i) % len(bank)]
            key = candidate["question_text"].lower()[:40]
            if key not in asked:
                return candidate
        return bank[idx]