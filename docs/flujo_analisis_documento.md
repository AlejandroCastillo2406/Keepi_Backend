# Flujo paso a paso: qué hace el endpoint con tu archivo (POST /mobile/analyze)

## 1. Entrada en el backend
- **Ruta:** `POST /api/v1/documents/mobile/analyze`
- **Body:** multipart con un único campo `file` (tu archivo).
- El backend recibe el archivo en memoria (`UploadFile`), lee todo el contenido con `await file.read()` y obtiene: `content` (bytes), `file.filename`, `file.content_type`.

## 2. DocumentService.analyze_document_only
- Recibe: `user_id`, `content` (bytes del archivo), `file_name`, `file_type`.
- No guarda nada en BD ni en Drive; solo orquesta el análisis y devuelve un diccionario.

## 3. Verificación de suscripción (SubscriptionService)
- Se llama a `subscription_service.check_analysis_limit(user_id, db)`.
- Si el usuario no puede analizar (límite gratuito superado, etc.), se devuelve de inmediato `SUBSCRIPTION_REQUIRED` (402) **sin tocar el archivo**.
- Si puede analizar, se continúa.

## 4. Extracción de texto del archivo (_extract_text)
Según el tipo MIME del archivo:

| Tipo | Qué se hace |
|------|-------------|
| **Imagen** (`image/*`) | AWS Textract (síncrono) sobre los bytes de la imagen. Si falla o devuelve poco texto → `MANUAL_CLASSIFICATION_REQUIRED`. |
| **PDF** (`application/pdf`) | AWS Textract **asíncrono**: se sube el PDF a S3 temporal, se lanza un job de análisis, se espera por polling hasta que termine y se extrae el texto de todas las páginas. Lento en PDFs grandes. Si falla o poco texto → manual. |
| **Word** (docx/doc) | Biblioteca `python-docx` en memoria: se lee el .docx y se extrae texto de párrafos y tablas. Si falla o poco texto → manual. |
| **Excel** (xlsx/xls) | Biblioteca `openpyxl`: se lee el libro y se concatena el texto de las celdas. Si falla o poco texto → manual. |
| **PowerPoint** (pptx) | Biblioteca `python-pptx`: se recorre cada slide y cada shape con texto. Si falla o poco texto → manual. |
| **Otro** | Se intenta decodificar los bytes como UTF-8; si no, se devuelve algo genérico tipo "Archivo: nombre". |

Resultado de este paso: una cadena `extracted_text` (el texto del documento).

## 5. Una sola llamada a Bedrock (optimizado)
- Se llama **una vez** a `bedrock_service.analyze_document_content(extracted_text, filename)`.
- El prompt pide en un solo JSON: **categoría**, **confianza** (0–1), **fecha de vencimiento**, **document_number**, **organization**, **tags**.
- Claude devuelve un JSON; se parsea y se obtienen todos los campos.
- Si la categoría es "MANUAL_CLASSIFICATION_REQUIRED", se devuelve esa respuesta y se termina.
- Si Bedrock no devuelve fecha de vencimiento, se usa fallback por regex (`_extract_expiry_date_regex_only`). Si no devuelve número u organización, se usan `_extract_document_number` y `_extract_organization` (regex).

## 6. Tags por palabras clave (sin Bedrock)
- Se combinan los tags devueltos por Bedrock con tags locales por palabras clave (`_merge_keyword_tags`: urgente, importante, académico, laboral, etc.). Solo CPU.

## 7. Metadatos (regex, sin Bedrock)
- `_extract_metadata(extracted_text)`: fechas, montos y números de documento con regex. Rápido.

## 8. Incremento del contador de análisis
- `subscription_service.increment_analysis_usage(user_id, db)`.

## 9. Respuesta final
- Se construye el diccionario con: `suggested_category`, `confidence_score`, `extracted_text`, `metadata`, `tags`, `expiry_date`, `document_number`, `organization`, etc.
- `analyze_document_only` lo adapta al formato del móvil (`category`, `recommended_name`, etc.) y lo devuelve.

---

## Resumen de dónde se gasta tiempo (después de la optimización)
1. **Lectura del archivo**: rápido.
2. **Verificación de suscripción** (BD): rápido.
3. **Extracción de texto**: puede ser **muy lenta** en PDFs (Textract asíncrono).
4. **Bedrock**: **1 sola llamada** (categoría, confianza, fecha, número, organización, tags). Antes eran 4 llamadas.
5. **Metadatos y tags locales** (regex): rápido.
