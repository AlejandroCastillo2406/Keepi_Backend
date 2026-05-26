import asyncio
import logging
import re
import time
import unicodedata
from typing import Any, Dict, List

import boto3

from app.config.settings import Settings

logger = logging.getLogger(__name__)
settings = Settings()


class AWSService:

    def __init__(self):
        self.textract_client = boto3.client(
            "textract",
            region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
        )
        self.comprehend_client = boto3.client(
            "comprehend",
            region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
        )
        self.s3_client = boto3.client(
            "s3",
            region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
        )

    async def extract_text_from_document(
        self, file_data: bytes, file_name: str, file_type: str
    ) -> Dict[str, Any]:
        try:
            logger.info("Extrayendo texto de %s (tipo: %s)", file_name, file_type)
            logger.info("Tamaño del archivo: %d bytes", len(file_data))

            if file_type.lower() in ["pdf", "application/pdf"]:
                logger.info("Procesando PDF con Textract asíncrono")

                try:
                    textract_result = await self._extract_text_with_textract_async(
                        file_data, file_name
                    )
                    if (
                        textract_result
                        and len(textract_result.get("text", "").strip()) > 100
                    ):
                        logger.info(
                            "Textract extrajo %d caracteres",
                            len(textract_result["text"]),
                        )
                        logger.info(
                            f"📝 Primeros 500 caracteres: {textract_result['text'][:500]}..."
                        )
                        logger.info(
                            f"📝 Últimos 200 caracteres: ...{textract_result['text'][-200:]}"
                        )
                        return textract_result
                    else:
                        logger.warning("Textract no extrajo texto suficiente")
                        return {
                            "text": "",
                            "confidence": 0.0,
                            "method": "textract_failed",
                            "blocks_count": 0,
                            "line_blocks_count": 0,
                            "word_blocks_count": 0,
                            "block_types": {},
                            "raw_response": {},
                        }
                except Exception:
                    logger.exception("Error en Textract asíncrono")
                    return {
                        "text": "",
                        "confidence": 0.0,
                        "method": "textract_error",
                        "blocks_count": 0,
                        "line_blocks_count": 0,
                        "word_blocks_count": 0,
                        "block_types": {},
                        "raw_response": {},
                    }

            elif file_type.lower() in ["image/jpeg", "image/jpg", "image/png"]:
                logger.info("Procesando imagen con AWS Textract síncrono...")
                return await self._extract_text_from_image(file_data)

            else:
                logger.warning("Tipo de archivo no soportado: %s", file_type)
                return {
                    "text": "",
                    "confidence": 0.0,
                    "method": "unsupported",
                    "blocks_count": 0,
                    "line_blocks_count": 0,
                    "word_blocks_count": 0,
                    "block_types": {},
                    "raw_response": {},
                }

        except Exception:
            logger.exception("Error en extracción de texto")
            raise

    async def _extract_text_with_textract_async(
        self, file_data: bytes, file_name: str
    ) -> Dict[str, Any]:
        try:
            logger.info("Iniciando análisis asíncrono con Textract")

            temp_s3_key = f"temp/{file_name}"
            logger.info(f"📤 Subiendo archivo a S3: {temp_s3_key}")

            self.s3_client.put_object(
                Bucket=settings.aws_s3_bucket,
                Key=temp_s3_key,
                Body=file_data,
                ContentType="application/pdf",
            )

            logger.info("🚀 Iniciando StartDocumentAnalysis...")
            response = self.textract_client.start_document_analysis(
                DocumentLocation={
                    "S3Object": {"Bucket": settings.aws_s3_bucket, "Name": temp_s3_key}
                },
                FeatureTypes=["TABLES", "FORMS"],
            )

            job_id = response["JobId"]
            logger.info(f"📋 Job ID: {job_id}")

            logger.info("⏳ Esperando a que termine el análisis...")
            max_attempts = 60
            attempt = 0

            while attempt < max_attempts:
                response = self.textract_client.get_document_analysis(JobId=job_id)
                status = response["JobStatus"]

                logger.info("Estado del análisis (intento %d): %s", attempt + 1, status)

                if status == "SUCCEEDED":
                    logger.info("Análisis completado")
                    break
                elif status == "FAILED":
                    error_message = response.get("StatusMessage", "Error desconocido")
                    logger.error("Análisis falló: %s", error_message)
                    raise Exception(f"Análisis de Textract falló: {error_message}")
                elif status == "PARTIAL_SUCCESS":
                    logger.warning("Análisis completado parcialmente")
                    break

                await asyncio.sleep(5)
                attempt += 1

            if attempt >= max_attempts:
                raise Exception("Timeout: El análisis tardó demasiado")

            logger.info("📝 Extrayendo texto de todas las páginas...")
            all_text = ""
            all_blocks = []
            next_token = None
            page_count = 0

            while True:
                if next_token:
                    response = self.textract_client.get_document_analysis(
                        JobId=job_id, NextToken=next_token
                    )
                else:
                    response = self.textract_client.get_document_analysis(JobId=job_id)

                blocks = response.get("Blocks", [])
                all_blocks.extend(blocks)

                for block in blocks:
                    if block["BlockType"] == "LINE":
                        all_text += block["Text"] + " "
                    elif block["BlockType"] == "PAGE":
                        page_count += 1

                next_token = response.get("NextToken")
                if not next_token:
                    break

            try:
                self.s3_client.delete_object(
                    Bucket=settings.aws_s3_bucket, Key=temp_s3_key
                )
                logger.info("🗑️ Archivo temporal eliminado de S3")
            except Exception as e:
                logger.warning("No se pudo eliminar archivo temporal: %s", e)

            line_blocks = [b for b in all_blocks if b["BlockType"] == "LINE"]
            word_blocks = [b for b in all_blocks if b["BlockType"] == "WORD"]

            block_types = {}
            for block in all_blocks:
                block_type = block["BlockType"]
                block_types[block_type] = block_types.get(block_type, 0) + 1

            logger.info("Estadísticas del análisis:")
            logger.info(f"   - Páginas procesadas: {page_count}")
            logger.info(f"   - Bloques totales: {len(all_blocks)}")
            logger.info(f"   - Líneas de texto: {len(line_blocks)}")
            logger.info(f"   - Palabras: {len(word_blocks)}")
            logger.info(f"   - Caracteres extraídos: {len(all_text)}")

            return {
                "text": all_text.strip(),
                "confidence": 0.95,
                "method": "textract_async_multipage",
                "blocks_count": len(all_blocks),
                "line_blocks_count": len(line_blocks),
                "word_blocks_count": len(word_blocks),
                "block_types": block_types,
                "raw_response": {
                    "job_id": job_id,
                    "pages_processed": page_count,
                    "total_blocks": len(all_blocks),
                },
            }

        except Exception:
            logger.exception("Error en Textract asíncrono")
            raise

    async def _extract_text_from_image(self, image_data: bytes) -> Dict[str, Any]:
        try:
            logger.info("Procesando imagen con AWS Textract síncrono...")

            response = self.textract_client.detect_document_text(
                Document={"Bytes": image_data}
            )

            text = ""
            blocks = response.get("Blocks", [])
            line_blocks = [b for b in blocks if b["BlockType"] == "LINE"]
            word_blocks = [b for b in blocks if b["BlockType"] == "WORD"]

            for block in line_blocks:
                text += block["Text"] + " "

            block_types = {}
            for block in blocks:
                block_type = block["BlockType"]
                block_types[block_type] = block_types.get(block_type, 0) + 1

            logger.info(
                "Imagen procesada: %d caracteres, %d líneas",
                len(text),
                len(line_blocks),
            )

            return {
                "text": text.strip(),
                "confidence": 0.90,
                "method": "textract_sync_image",
                "blocks_count": len(blocks),
                "line_blocks_count": len(line_blocks),
                "word_blocks_count": len(word_blocks),
                "block_types": block_types,
                "raw_response": response,
            }

        except Exception:
            logger.exception("Error procesando imagen")
            raise

    async def categorize_document(self, text: str) -> Dict[str, Any]:
        try:
            logger.info("Analizando texto con Comprehend")
            logger.info("Longitud del texto: %d caracteres", len(text))
            logger.info(f"📝 Primeros 200 caracteres: {text[:200]}...")
            logger.info(f"📝 Últimos 200 caracteres: ...{text[-200:]}")

            chunks = self._split_text_into_chunks(text, max_chunk_size=4500)
            logger.info(f"Texto dividido en {len(chunks)} chunks")

            all_entities = []
            all_key_phrases = []
            sentiments = []
            total_confidence = 0

            for i, chunk in enumerate(chunks):
                logger.debug(
                    "Procesando chunk %d/%d (%d caracteres)",
                    i + 1,
                    len(chunks),
                    len(chunk),
                )

                try:

                    entities_response = self.comprehend_client.detect_entities(
                        Text=chunk, LanguageCode="es"
                    )
                    entities = entities_response.get("Entities", [])
                    all_entities.extend(entities)

                    key_phrases_response = self.comprehend_client.detect_key_phrases(
                        Text=chunk, LanguageCode="es"
                    )
                    key_phrases = key_phrases_response.get("KeyPhrases", [])
                    all_key_phrases.extend(key_phrases)

                    sentiment_response = self.comprehend_client.detect_sentiment(
                        Text=chunk, LanguageCode="es"
                    )
                    sentiments.append(sentiment_response.get("Sentiment", "NEUTRAL"))

                    logger.info(f"   - Entidades: {len(entities)}")
                    logger.info(f"   - Frases clave: {len(key_phrases)}")
                    logger.info(
                        f"   - Sentimiento: {sentiment_response.get('Sentiment', 'NEUTRAL')}"
                    )

                except Exception as e:
                    logger.warning("Error procesando chunk %d: %s", i + 1, e)
                    continue

            category = self._determine_document_category(all_entities, all_key_phrases)

            if sentiments:
                sentiment_scores = [
                    s.get("SentimentScore", {}).get("Mixed", 0)
                    for s in sentiments
                    if isinstance(s, dict)
                ]
                total_confidence = (
                    sum(sentiment_scores) / len(sentiment_scores)
                    if sentiment_scores
                    else 0.5
                )
            else:
                total_confidence = 0.7

            logger.info(f"🎯 CATEGORÍA DETERMINADA: {category}")
            logger.info("Confianza: %.2f", total_confidence)
            logger.info(f"📈 Total entidades: {len(all_entities)}")
            logger.info(f"📈 Total frases clave: {len(all_key_phrases)}")

            return {
                "category": category,
                "confidence": total_confidence,
                "entities": all_entities,
                "key_phrases": all_key_phrases,
                "sentiments": sentiments,
                "chunks_processed": len(chunks),
                "text_length": len(text),
            }

        except Exception as e:
            logger.exception("Error en categorización")
            return {
                "category": "Documento",
                "confidence": 0.0,
                "entities": [],
                "key_phrases": [],
                "sentiments": [],
                "chunks_processed": 0,
                "text_length": len(text),
                "error": str(e),
            }

    def _split_text_into_chunks(
        self, text: str, max_chunk_size: int = 4500
    ) -> List[str]:
        if len(text.encode("utf-8")) <= max_chunk_size:
            return [text]

        chunks = []
        current_chunk = ""

        paragraphs = text.split("\n\n")

        for paragraph in paragraphs:
            paragraph_bytes = paragraph.encode("utf-8")

            if len(paragraph_bytes) > max_chunk_size:
                sentences = paragraph.split(". ")
                for sentence in sentences:
                    sentence_bytes = sentence.encode("utf-8")

                    if (
                        len(current_chunk.encode("utf-8")) + len(sentence_bytes)
                        > max_chunk_size
                    ):
                        if current_chunk:
                            chunks.append(current_chunk.strip())
                            current_chunk = sentence
                        else:

                            words = sentence.split()
                            for word in words:
                                word_bytes = word.encode("utf-8")
                                if (
                                    len(current_chunk.encode("utf-8")) + len(word_bytes)
                                    > max_chunk_size
                                ):
                                    if current_chunk:
                                        chunks.append(current_chunk.strip())
                                        current_chunk = word
                                    else:
                                        chunks.append(word)
                                else:
                                    current_chunk += (
                                        " " + word if current_chunk else word
                                    )
                    else:
                        current_chunk += ". " + sentence if current_chunk else sentence
            else:
                if (
                    len(current_chunk.encode("utf-8")) + len(paragraph_bytes)
                    > max_chunk_size
                ):
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                        current_chunk = paragraph
                    else:
                        chunks.append(paragraph)
                else:
                    current_chunk += "\n\n" + paragraph if current_chunk else paragraph

        if current_chunk:
            chunks.append(current_chunk.strip())

        return chunks

    def _determine_document_category(
        self, entities: List[Dict], key_phrases: List[Dict]
    ) -> str:

        logger.info(
            f"Analizando {len(entities)} entidades y {len(key_phrases)} frases clave para categorización dinámica con IA"
        )

        entity_category = self._analyze_entities_dynamically(entities)
        if entity_category and entity_category != "Documento":
            logger.info("Categoría por entidades: %s", entity_category)
            return entity_category

        phrase_category = self._analyze_phrases_dynamically(key_phrases)
        if phrase_category and phrase_category != "Documento":
            logger.info("Categoría por frases: %s", phrase_category)
            return phrase_category

        combined_category = self._analyze_combined_dynamically(entities, key_phrases)
        if combined_category and combined_category != "Documento":
            logger.info("Categoría combinada: %s", combined_category)
            return combined_category

        logger.warning("No se pudo determinar categoría, usando Documento")
        return "Documento"

    def _analyze_entities_dynamically(self, entities: List[Dict]) -> str:
        if not entities:
            return "Documento"

        entity_types = {}
        for entity in entities:
            entity_type = entity.get("Type", "")
            score = entity.get("Score", 0)

            if entity_type not in entity_types:
                entity_types[entity_type] = {
                    "count": 0,
                    "total_score": 0,
                    "entities": [],
                }

            entity_types[entity_type]["count"] += 1
            entity_types[entity_type]["total_score"] += score
            entity_types[entity_type]["entities"].append(entity)

        for entity_type in entity_types:
            entity_types[entity_type]["avg_score"] = (
                entity_types[entity_type]["total_score"]
                / entity_types[entity_type]["count"]
            )

        if (
            "ORGANIZATION" in entity_types
            and entity_types["ORGANIZATION"]["avg_score"] > 0.7
        ):
            return "Organización"
        elif "PERSON" in entity_types and entity_types["PERSON"]["avg_score"] > 0.7:
            return "Personal"
        elif "LOCATION" in entity_types and entity_types["LOCATION"]["avg_score"] > 0.7:
            return "Ubicación"
        elif "DATE" in entity_types and entity_types["DATE"]["avg_score"] > 0.7:
            return "Temporal"
        elif "QUANTITY" in entity_types and entity_types["QUANTITY"]["avg_score"] > 0.7:
            return "Financiero"

        return "Documento"

    def _analyze_phrases_dynamically(self, key_phrases: List[Dict]) -> str:
        if not key_phrases:
            return "Documento"

        sorted_phrases = sorted(
            key_phrases, key=lambda x: x.get("Score", 0), reverse=True
        )

        for phrase in sorted_phrases[:10]:
            text = phrase.get("Text", "").lower()
            score = phrase.get("Score", 0)

            if score < 0.5:
                continue

            if any(
                word in text
                for word in [
                    "factura",
                    "recibo",
                    "pago",
                    "cobro",
                    "precio",
                    "total",
                    "importe",
                ]
            ):
                return "Financiero"
            elif any(
                word in text
                for word in [
                    "contrato",
                    "acuerdo",
                    "términos",
                    "condiciones",
                    "cláusula",
                ]
            ):
                return "Legal"
            elif any(
                word in text
                for word in [
                    "técnico",
                    "especificación",
                    "manual",
                    "instrucción",
                    "procedimiento",
                ]
            ):
                return "Técnico"
            elif any(
                word in text
                for word in [
                    "médico",
                    "salud",
                    "paciente",
                    "diagnóstico",
                    "tratamiento",
                ]
            ):
                return "Médico"
            elif any(
                word in text
                for word in [
                    "académico",
                    "estudio",
                    "investigación",
                    "trabajo",
                    "proyecto",
                ]
            ):
                return "Académico"

        return "Documento"

    def _analyze_combined_dynamically(
        self, entities: List[Dict], key_phrases: List[Dict]
    ) -> str:
        if not entities and not key_phrases:
            return "Documento"

        entity_category = self._analyze_entities_dynamically(entities)
        phrase_category = self._analyze_phrases_dynamically(key_phrases)

        if entity_category == phrase_category and entity_category != "Documento":
            return entity_category

        if entity_category != "Documento":
            return entity_category

        if phrase_category != "Documento":
            return phrase_category

        return "Documento"

    async def create_user_folders(self, user_id: str) -> Dict[str, str]:
        try:

            temp_key = f"users/{user_id}/temp/"
            self.s3_client.put_object(Bucket=settings.aws_s3_bucket, Key=temp_key)

            categorias_key = f"users/{user_id}/categorias/"
            self.s3_client.put_object(Bucket=settings.aws_s3_bucket, Key=categorias_key)

            logger.info("Carpetas creadas para usuario %s", user_id)
            return {"temp_folder": temp_key, "categorias_folder": categorias_key}
        except Exception:
            logger.exception("Error creando carpetas")
            raise

    async def create_category_folder(self, user_id: str, category: str) -> str:
        try:
            sanitized_category = self._sanitize_folder_name(category)
            category_key = f"users/{user_id}/categorias/{sanitized_category}/"
            self.s3_client.put_object(Bucket=settings.aws_s3_bucket, Key=category_key)

            logger.info("Carpeta de categoría creada: %s", category_key)
            return category_key
        except Exception:
            logger.exception("Error creando carpeta de categoría")
            raise

    async def upload_to_s3_temp(
        self, file_data: bytes, file_name: str, user_id: str
    ) -> str:
        try:
            key = f"users/{user_id}/temp/{file_name}"
            self.s3_client.put_object(
                Bucket=settings.aws_s3_bucket, Key=key, Body=file_data
            )

            file_url = f"https://{settings.aws_s3_bucket}.s3.amazonaws.com/{key}"
            logger.info("Archivo subido a S3: %s", file_url)
            return file_url

        except Exception:
            logger.exception("Error subiendo archivo a S3")
            raise

    async def upload_to_s3_with_folder(
        self,
        file_data: bytes,
        file_name: str,
        user_id: str,
        folder_name: str,
        content_type: str | None = None,
    ) -> str:
        try:

            from app.utils.doctor_patient_storage import sanitize_s3_relative_path

            clean_folder = sanitize_s3_relative_path(folder_name)

            category_ascii = self._to_ascii_safe(folder_name)
            key = f"users/{user_id}/{clean_folder}/{file_name}"

            logger.info("Subiendo archivo a carpeta de categoría: %s", key)

            put_kwargs = {
                "Bucket": settings.aws_s3_bucket,
                "Key": key,
                "Body": file_data,
                "Metadata": {
                    "user_id": user_id,
                    "category": category_ascii,
                    "folder": clean_folder,
                    "uploaded_at": str(int(time.time())),
                },
            }
            if content_type:
                put_kwargs["ContentType"] = content_type
            self.s3_client.put_object(**put_kwargs)

            file_url = f"https://{settings.aws_s3_bucket}.s3.amazonaws.com/{key}"
            logger.info("Archivo subido a carpeta de categoría: %s", file_url)
            return file_url

        except Exception:
            logger.exception("Error subiendo archivo a carpeta de categoría")
            raise

    async def move_file_in_s3(
        self, user_id: str, file_name: str, from_folder: str, to_folder: str
    ) -> str:
        try:
            source_key = f"users/{user_id}/{from_folder}/{file_name}"
            dest_key = f"users/{user_id}/{to_folder}/{file_name}"

            copy_source = {"Bucket": settings.aws_s3_bucket, "Key": source_key}
            self.s3_client.copy_object(
                CopySource=copy_source, Bucket=settings.aws_s3_bucket, Key=dest_key
            )

            self.s3_client.delete_object(Bucket=settings.aws_s3_bucket, Key=source_key)

            file_url = f"https://{settings.aws_s3_bucket}.s3.amazonaws.com/{dest_key}"
            logger.info("Archivo movido: %s -> %s", source_key, dest_key)
            return file_url
        except Exception:
            logger.exception("Error moviendo archivo")
            raise

    def _sanitize_folder_name(self, folder_name: str) -> str:
        try:

            normalized = unicodedata.normalize("NFD", folder_name)

            ascii_name = normalized.encode("ascii", "ignore").decode("ascii")

            if not ascii_name.strip():
                ascii_name = folder_name

            sanitized = re.sub(r"[^a-zA-Z0-9\-_]", "_", ascii_name)

            return sanitized[:50]
        except Exception as e:
            logger.warning(
                f"Error sanitizando nombre de carpeta, usando versión básica: {e}"
            )

            sanitized = re.sub(r"[^a-zA-Z0-9\-_]", "_", folder_name)
            return sanitized[:50]

    def _to_ascii_safe(self, text: str) -> str:
        try:

            normalized = unicodedata.normalize("NFD", text)

            ascii_text = normalized.encode("ascii", "ignore").decode("ascii")

            if not ascii_text.strip():

                ascii_text = re.sub(r"[^\x00-\x7F]+", " ", text)

            ascii_text = re.sub(r"\s+", " ", ascii_text.strip())
            return ascii_text[:100] if len(ascii_text) > 100 else ascii_text
        except Exception as e:
            logger.warning(f"Error convirtiendo a ASCII: {e}")

            ascii_text = re.sub(r"[^\x00-\x7F]+", " ", text)
            return re.sub(r"\s+", " ", ascii_text.strip())[:100]
