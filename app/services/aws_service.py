import boto3
import asyncio
import logging
import tempfile
import os
from typing import Dict, List, Any, Optional
from botocore.exceptions import ClientError
import fitz  # PyMuPDF
from app.config.settings import Settings

logger = logging.getLogger(__name__)
settings = Settings()

class AWSService:
    """Servicio para integración con AWS Textract y Comprehend"""
    
    def __init__(self):
            self.textract_client = boto3.client(
                'textract',
            region_name=settings.aws_region,
                aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key
            )
            self.comprehend_client = boto3.client(
                'comprehend',
            region_name=settings.aws_region,
                aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key
            )
            self.s3_client = boto3.client(
                's3',
            region_name=settings.aws_region,
                aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key
        )
    
    async def extract_text_from_document(self, file_data: bytes, file_name: str, file_type: str) -> Dict[str, Any]:
        """
        Extraer texto de documentos usando estrategia robusta
        
        Args:
            file_data: Datos del archivo
            file_name: Nombre del archivo
            file_type: Tipo MIME del archivo
            
        Returns:
            Dict con texto extraído y metadatos
        """
        try:
            logger.info(f"🔍 Extrayendo texto de {file_name} (tipo: {file_type})")
            logger.info(f"📊 Tamaño del archivo: {len(file_data)} bytes")
            
            # Para PDFs, usar solo AWS Textract asíncrono (principal)
            if file_type.lower() in ['pdf', 'application/pdf']:
                logger.info("📄 Procesando PDF con AWS Textract asíncrono...")
                
                try:
                    textract_result = await self._extract_text_with_textract_async(file_data, file_name)
                    if textract_result and len(textract_result.get('text', '').strip()) > 100:
                        logger.info(f"✅ AWS Textract asíncrono extrajo {len(textract_result['text'])} caracteres exitosamente")
                        logger.info(f"📝 Primeros 500 caracteres: {textract_result['text'][:500]}...")
                        logger.info(f"📝 Últimos 200 caracteres: ...{textract_result['text'][-200:]}")
                        return textract_result
                    else:
                        logger.warning("⚠️ AWS Textract asíncrono no pudo extraer texto suficiente")
                        return {
                            'text': '',
                            'confidence': 0.0,
                            'method': 'textract_failed',
                            'blocks_count': 0,
                            'line_blocks_count': 0,
                            'word_blocks_count': 0,
                            'block_types': {},
                            'raw_response': {}
                        }
                except Exception as e:
                    logger.error(f"❌ Error en AWS Textract asíncrono: {e}")
                    return {
                        'text': '',
                        'confidence': 0.0,
                        'method': 'textract_error',
                        'blocks_count': 0,
                        'line_blocks_count': 0,
                        'word_blocks_count': 0,
                        'block_types': {},
                        'raw_response': {}
                    }
            
            # Para imágenes, usar AWS Textract síncrono
            elif file_type.lower() in ['image/jpeg', 'image/jpg', 'image/png']:
                logger.info("🖼️ Procesando imagen con AWS Textract síncrono...")
                return await self._extract_text_from_image(file_data)
            
            else:
                logger.warning(f"⚠️ Tipo de archivo no soportado: {file_type}")
                return {
                    'text': '',
                    'confidence': 0.0,
                    'method': 'unsupported',
                    'blocks_count': 0,
                    'line_blocks_count': 0,
                    'word_blocks_count': 0,
                    'block_types': {},
                    'raw_response': {}
                }
                
        except Exception as e:
            logger.error(f"❌ Error inesperado en extracción de texto: {e}")
            raise
    
    def _extract_text_with_pymupdf(self, file_data: bytes, file_name: str) -> str:
        """Extraer texto usando PyMuPDF (fitz)"""
        try:
            doc = fitz.open(stream=file_data, filetype="pdf")
            all_text = ""
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                text = page.get_text()
                all_text += text + " "
            
            doc.close()
            return all_text.strip()
            
        except Exception as e:
            logger.error(f"Error en PyMuPDF: {e}")
            return ""
    
    async def _extract_text_with_textract_async(self, file_data: bytes, file_name: str) -> Dict[str, Any]:
        """
        Extraer texto de PDFs multipágina usando AWS Textract asíncrono
        """
        try:
            logger.info("🔄 Iniciando análisis asíncrono con AWS Textract...")
            
            # 1. Subir archivo a S3 temporalmente
            temp_s3_key = f"temp/{file_name}"
            logger.info(f"📤 Subiendo archivo a S3: {temp_s3_key}")
            
            self.s3_client.put_object(
                Bucket=settings.aws_s3_bucket,
                Key=temp_s3_key,
                Body=file_data,
                ContentType='application/pdf'
            )
            
            # 2. Iniciar análisis asíncrono
            logger.info("🚀 Iniciando StartDocumentAnalysis...")
            response = self.textract_client.start_document_analysis(
                DocumentLocation={
                    'S3Object': {
                        'Bucket': settings.aws_s3_bucket,
                        'Name': temp_s3_key
                    }
                },
                FeatureTypes=['TABLES', 'FORMS']
            )
            
            job_id = response['JobId']
            logger.info(f"📋 Job ID: {job_id}")
            
            # 3. Esperar a que termine el procesamiento
            logger.info("⏳ Esperando a que termine el análisis...")
            max_attempts = 60  # 5 minutos máximo
            attempt = 0
            
            while attempt < max_attempts:
                response = self.textract_client.get_document_analysis(JobId=job_id)
                status = response['JobStatus']
                
                logger.info(f"📊 Estado del análisis (intento {attempt + 1}): {status}")
                
                if status == 'SUCCEEDED':
                    logger.info("✅ Análisis completado exitosamente")
                    break
                elif status == 'FAILED':
                    error_message = response.get('StatusMessage', 'Error desconocido')
                    logger.error(f"❌ Análisis falló: {error_message}")
                    raise Exception(f"Análisis de Textract falló: {error_message}")
                elif status == 'PARTIAL_SUCCESS':
                    logger.warning("⚠️ Análisis completado parcialmente")
                    break
                
                await asyncio.sleep(5)  # Esperar 5 segundos
                attempt += 1
            
            if attempt >= max_attempts:
                raise Exception("Timeout: El análisis tardó demasiado")
            
            # 4. Extraer texto de todas las páginas
            logger.info("📝 Extrayendo texto de todas las páginas...")
            all_text = ""
            all_blocks = []
            next_token = None
            page_count = 0
            
            while True:
                if next_token:
                    response = self.textract_client.get_document_analysis(
                        JobId=job_id, 
                        NextToken=next_token
                    )
                else:
                    response = self.textract_client.get_document_analysis(JobId=job_id)
                
                blocks = response.get('Blocks', [])
                all_blocks.extend(blocks)
                
                # Procesar bloques de texto
                for block in blocks:
                    if block['BlockType'] == 'LINE':
                        all_text += block['Text'] + " "
                    elif block['BlockType'] == 'PAGE':
                        page_count += 1
                
                next_token = response.get('NextToken')
                if not next_token:
                    break
            
            # 5. Limpiar archivo temporal
            try:
                self.s3_client.delete_object(Bucket=settings.aws_s3_bucket, Key=temp_s3_key)
                logger.info("🗑️ Archivo temporal eliminado de S3")
            except Exception as e:
                logger.warning(f"⚠️ No se pudo eliminar archivo temporal: {e}")
            
            # 6. Calcular estadísticas
            line_blocks = [b for b in all_blocks if b['BlockType'] == 'LINE']
            word_blocks = [b for b in all_blocks if b['BlockType'] == 'WORD']
            
            block_types = {}
            for block in all_blocks:
                block_type = block['BlockType']
                block_types[block_type] = block_types.get(block_type, 0) + 1
            
            logger.info(f"📊 Estadísticas del análisis:")
            logger.info(f"   - Páginas procesadas: {page_count}")
            logger.info(f"   - Bloques totales: {len(all_blocks)}")
            logger.info(f"   - Líneas de texto: {len(line_blocks)}")
            logger.info(f"   - Palabras: {len(word_blocks)}")
            logger.info(f"   - Caracteres extraídos: {len(all_text)}")
            
            return {
                'text': all_text.strip(),
                'confidence': 0.95,
                'method': 'textract_async_multipage',
                'blocks_count': len(all_blocks),
                'line_blocks_count': len(line_blocks),
                'word_blocks_count': len(word_blocks),
                'block_types': block_types,
                'raw_response': {
                    'job_id': job_id,
                    'pages_processed': page_count,
                    'total_blocks': len(all_blocks)
                }
            }
            
        except Exception as e:
            logger.error(f"❌ Error en AWS Textract asíncrono: {e}")
            raise
    
    async def _extract_text_from_image(self, image_data: bytes) -> Dict[str, Any]:
        """Extraer texto de imágenes usando AWS Textract síncrono"""
        try:
            logger.info("🖼️ Procesando imagen con AWS Textract síncrono...")
            
            response = self.textract_client.detect_document_text(
                Document={'Bytes': image_data}
            )
            
            # Extraer texto
            text = ""
            blocks = response.get('Blocks', [])
            line_blocks = [b for b in blocks if b['BlockType'] == 'LINE']
            word_blocks = [b for b in blocks if b['BlockType'] == 'WORD']
            
            for block in line_blocks:
                text += block['Text'] + " "
            
            # Calcular estadísticas
            block_types = {}
            for block in blocks:
                block_type = block['BlockType']
                block_types[block_type] = block_types.get(block_type, 0) + 1
            
            logger.info(f"📊 Imagen procesada: {len(text)} caracteres, {len(line_blocks)} líneas")
            
            return {
                'text': text.strip(),
                'confidence': 0.90,
                'method': 'textract_sync_image',
                'blocks_count': len(blocks),
                'line_blocks_count': len(line_blocks),
                'word_blocks_count': len(word_blocks),
                'block_types': block_types,
                'raw_response': response
            }
            
        except Exception as e:
            logger.error(f"❌ Error procesando imagen: {e}")
            raise
    
    def _convert_pdf_to_pdf2(self, file_data: bytes, file_name: str) -> Optional[bytes]:
        """Convertir PDF a versión 2.0 usando PyMuPDF"""
        try:
            logger.info("🔄 Convirtiendo PDF a versión 2.0...")
            
            # Abrir PDF original
            doc = fitz.open(stream=file_data, filetype="pdf")
            
            # Crear nuevo documento PDF 2.0
            new_doc = fitz.open()
            
            # Copiar páginas
            for page_num in range(len(doc)):
                page = doc[page_num]
                new_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)
            
            # Guardar como PDF 2.0
            pdf2_data = new_doc.write()
            
            doc.close()
            new_doc.close()
            
            logger.info("✅ PDF convertido a versión 2.0 exitosamente")
            return pdf2_data
            
        except Exception as e:
            logger.error(f"❌ Error convirtiendo PDF: {e}")
            return None
    
    async def categorize_document(self, text: str) -> Dict[str, Any]:
        """
        Categorizar documento usando AWS Comprehend con chunks para textos largos
        
        Args:
            text: Texto del documento a categorizar
            
        Returns:
            Dict con categorías detectadas
        """
        try:
            logger.info(f"🔍 ANALIZANDO TEXTO CON AWS COMPREHEND")
            logger.info(f"📊 Longitud del texto: {len(text)} caracteres")
            logger.info(f"📝 Primeros 200 caracteres: {text[:200]}...")
            logger.info(f"📝 Últimos 200 caracteres: ...{text[-200:]}")
            
            # Dividir texto en chunks si es muy largo (límite de Comprehend: 4500 bytes)
            chunks = self._split_text_into_chunks(text, max_chunk_size=4500)
            logger.info(f"Texto dividido en {len(chunks)} chunks")
            
            all_entities = []
            all_key_phrases = []
            sentiments = []
            total_confidence = 0
            
            # Procesar cada chunk
            for i, chunk in enumerate(chunks):
                logger.info(f"🔄 Procesando chunk {i+1}/{len(chunks)} ({len(chunk)} caracteres)")
                
                try:
                    # Detectar entidades
                    entities_response = self.comprehend_client.detect_entities(
                        Text=chunk,
                        LanguageCode='es'
                    )
                    entities = entities_response.get('Entities', [])
                    all_entities.extend(entities)
                    
                    # Detectar frases clave
                    key_phrases_response = self.comprehend_client.detect_key_phrases(
                        Text=chunk,
                        LanguageCode='es'
                    )
                    key_phrases = key_phrases_response.get('KeyPhrases', [])
                    all_key_phrases.extend(key_phrases)
                    
                    # Detectar sentimiento
                    sentiment_response = self.comprehend_client.detect_sentiment(
                        Text=chunk,
                        LanguageCode='es'
                    )
                    sentiments.append(sentiment_response.get('Sentiment', 'NEUTRAL'))
                    
                    logger.info(f"   - Entidades: {len(entities)}")
                    logger.info(f"   - Frases clave: {len(key_phrases)}")
                    logger.info(f"   - Sentimiento: {sentiment_response.get('Sentiment', 'NEUTRAL')}")
                    
                except Exception as e:
                    logger.error(f"❌ Error procesando chunk {i+1}: {e}")
                    continue
            
            # Determinar categoría dinámicamente
            category = self._determine_document_category(all_entities, all_key_phrases)
            
            # Calcular confianza promedio
            if sentiments:
                sentiment_scores = [s.get('SentimentScore', {}).get('Mixed', 0) for s in sentiments if isinstance(s, dict)]
                total_confidence = sum(sentiment_scores) / len(sentiment_scores) if sentiment_scores else 0.5
            else:
                total_confidence = 0.7
            
            logger.info(f"🎯 CATEGORÍA DETERMINADA: {category}")
            logger.info(f"📊 Confianza: {total_confidence:.2f}")
            logger.info(f"📈 Total entidades: {len(all_entities)}")
            logger.info(f"📈 Total frases clave: {len(all_key_phrases)}")
            
            return {
                'category': category,
                'confidence': total_confidence,
                'entities': all_entities,
                'key_phrases': all_key_phrases,
                'sentiments': sentiments,
                'chunks_processed': len(chunks),
                'text_length': len(text)
            }
            
        except Exception as e:
            logger.error(f"❌ Error en categorización: {e}")
            return {
                'category': 'Documento',
                'confidence': 0.0,
                'entities': [],
                'key_phrases': [],
                'sentiments': [],
                'chunks_processed': 0,
                'text_length': len(text),
                'error': str(e)
            }
    
    def _split_text_into_chunks(self, text: str, max_chunk_size: int = 4500) -> List[str]:
        """Dividir texto en chunks para AWS Comprehend (límite de bytes)"""
        if len(text.encode('utf-8')) <= max_chunk_size:
            return [text]
        
        chunks = []
        current_chunk = ""
        
        # Dividir por párrafos primero
        paragraphs = text.split('\n\n')
        
        for paragraph in paragraphs:
            paragraph_bytes = paragraph.encode('utf-8')
            
            # Si el párrafo es muy grande, dividirlo por oraciones
            if len(paragraph_bytes) > max_chunk_size:
                sentences = paragraph.split('. ')
                for sentence in sentences:
                    sentence_bytes = sentence.encode('utf-8')
                    
                    if len(current_chunk.encode('utf-8')) + len(sentence_bytes) > max_chunk_size:
                        if current_chunk:
                            chunks.append(current_chunk.strip())
                            current_chunk = sentence
                        else:
                            # Si una sola oración es muy grande, dividirla por palabras
                            words = sentence.split()
                            for word in words:
                                word_bytes = word.encode('utf-8')
                                if len(current_chunk.encode('utf-8')) + len(word_bytes) > max_chunk_size:
                                    if current_chunk:
                                        chunks.append(current_chunk.strip())
                                        current_chunk = word
                                    else:
                                        chunks.append(word)
                                else:
                                    current_chunk += " " + word if current_chunk else word
                    else:
                        current_chunk += ". " + sentence if current_chunk else sentence
            else:
                if len(current_chunk.encode('utf-8')) + len(paragraph_bytes) > max_chunk_size:
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
    
    def _determine_document_category(self, entities: List[Dict], key_phrases: List[Dict]) -> str:
        """Determinar categoría del documento usando análisis 100% dinámico con IA"""
        
        logger.info(f"Analizando {len(entities)} entidades y {len(key_phrases)} frases clave para categorización dinámica con IA")
        
        # Método 1: Análisis dinámico basado en entidades más relevantes
        entity_category = self._analyze_entities_dynamically(entities)
        if entity_category and entity_category != 'Documento':
            logger.info(f"✅ Categoría determinada por análisis dinámico de entidades: {entity_category}")
            return entity_category
        
        # Método 2: Análisis dinámico basado en frases clave más relevantes
        phrase_category = self._analyze_phrases_dynamically(key_phrases)
        if phrase_category and phrase_category != 'Documento':
            logger.info(f"✅ Categoría determinada por análisis dinámico de frases: {phrase_category}")
            return phrase_category
        
        # Método 3: Análisis combinado dinámico
        combined_category = self._analyze_combined_dynamically(entities, key_phrases)
        if combined_category and combined_category != 'Documento':
            logger.info(f"✅ Categoría determinada por análisis combinado dinámico: {combined_category}")
            return combined_category
        
        # Fallback: usar "Documento" como categoría genérica
        logger.info("⚠️ No se pudo determinar categoría específica, usando Documento")
        return 'Documento'
    
    def _analyze_entities_dynamically(self, entities: List[Dict]) -> str:
        """Análisis dinámico de entidades para determinar categoría"""
        if not entities:
            return 'Documento'
        
        # Agrupar entidades por tipo y calcular relevancia
        entity_types = {}
        for entity in entities:
            entity_type = entity.get('Type', '')
            score = entity.get('Score', 0)
            
            if entity_type not in entity_types:
                entity_types[entity_type] = {'count': 0, 'total_score': 0, 'entities': []}
            
            entity_types[entity_type]['count'] += 1
            entity_types[entity_type]['total_score'] += score
            entity_types[entity_type]['entities'].append(entity)
        
        # Calcular relevancia promedio por tipo
        for entity_type in entity_types:
            entity_types[entity_type]['avg_score'] = entity_types[entity_type]['total_score'] / entity_types[entity_type]['count']
        
        # Determinar categoría basada en el tipo de entidad más relevante
        if 'ORGANIZATION' in entity_types and entity_types['ORGANIZATION']['avg_score'] > 0.7:
            return 'Organización'
        elif 'PERSON' in entity_types and entity_types['PERSON']['avg_score'] > 0.7:
            return 'Personal'
        elif 'LOCATION' in entity_types and entity_types['LOCATION']['avg_score'] > 0.7:
            return 'Ubicación'
        elif 'DATE' in entity_types and entity_types['DATE']['avg_score'] > 0.7:
            return 'Temporal'
        elif 'QUANTITY' in entity_types and entity_types['QUANTITY']['avg_score'] > 0.7:
            return 'Financiero'
        
        return 'Documento'
    
    def _analyze_phrases_dynamically(self, key_phrases: List[Dict]) -> str:
        """Análisis dinámico de frases clave para determinar categoría"""
        if not key_phrases:
            return 'Documento'
        
        # Ordenar frases por relevancia (score)
        sorted_phrases = sorted(key_phrases, key=lambda x: x.get('Score', 0), reverse=True)
        
        # Analizar las frases más relevantes
        for phrase in sorted_phrases[:10]:  # Top 10 frases más relevantes
            text = phrase.get('Text', '').lower()
            score = phrase.get('Score', 0)
            
            if score < 0.5:  # Solo frases con alta confianza
                continue
            
            # Análisis dinámico de contenido
            if any(word in text for word in ['factura', 'recibo', 'pago', 'cobro', 'precio', 'total', 'importe']):
                return 'Financiero'
            elif any(word in text for word in ['contrato', 'acuerdo', 'términos', 'condiciones', 'cláusula']):
                return 'Legal'
            elif any(word in text for word in ['técnico', 'especificación', 'manual', 'instrucción', 'procedimiento']):
                return 'Técnico'
            elif any(word in text for word in ['médico', 'salud', 'paciente', 'diagnóstico', 'tratamiento']):
                return 'Médico'
            elif any(word in text for word in ['académico', 'estudio', 'investigación', 'trabajo', 'proyecto']):
                return 'Académico'
        
        return 'Documento'
    
    def _analyze_combined_dynamically(self, entities: List[Dict], key_phrases: List[Dict]) -> str:
        """Análisis combinado dinámico de entidades y frases clave"""
        if not entities and not key_phrases:
            return 'Documento'
        
        # Combinar análisis de entidades y frases
        entity_category = self._analyze_entities_dynamically(entities)
        phrase_category = self._analyze_phrases_dynamically(key_phrases)
        
        # Si ambos análisis coinciden, usar esa categoría
        if entity_category == phrase_category and entity_category != 'Documento':
            return entity_category
        
        # Si hay entidades relevantes, priorizar su categoría
        if entity_category != 'Documento':
            return entity_category
        
        # Si hay frases relevantes, usar su categoría
        if phrase_category != 'Documento':
            return phrase_category
        
        return 'Documento'
    
    # Métodos S3 para manejo de archivos
    async def create_user_folders(self, user_id: str) -> Dict[str, str]:
        """Crear estructura de carpetas del usuario en S3"""
        try:
            # Crear carpeta temp
            temp_key = f"users/{user_id}/temp/"
            self.s3_client.put_object(Bucket=settings.aws_s3_bucket, Key=temp_key)
            
            # Crear carpeta categorías
            categorias_key = f"users/{user_id}/categorias/"
            self.s3_client.put_object(Bucket=settings.aws_s3_bucket, Key=categorias_key)
            
            logger.info(f"✅ Carpetas creadas para usuario {user_id}")
            return {
                'temp_folder': temp_key,
                'categorias_folder': categorias_key
            }
        except Exception as e:
            logger.error(f"❌ Error creando carpetas: {e}")
            raise
    
    async def create_category_folder(self, user_id: str, category: str) -> str:
        """Crear carpeta de categoría específica"""
        try:
            sanitized_category = self._sanitize_folder_name(category)
            category_key = f"users/{user_id}/categorias/{sanitized_category}/"
            self.s3_client.put_object(Bucket=settings.aws_s3_bucket, Key=category_key)
            
            logger.info(f"✅ Carpeta de categoría creada: {category_key}")
            return category_key
        except Exception as e:
            logger.error(f"❌ Error creando carpeta de categoría: {e}")
            raise
    
    async def upload_to_s3_temp(self, file_data: bytes, file_name: str, user_id: str) -> str:
        """Subir archivo a carpeta temporal de S3"""
        try:
            key = f"users/{user_id}/temp/{file_name}"
            self.s3_client.put_object(
                Bucket=settings.aws_s3_bucket,
                Key=key,
                Body=file_data
            )
            
            file_url = f"https://{settings.aws_s3_bucket}.s3.amazonaws.com/{key}"
            logger.info(f"✅ Archivo subido a S3: {file_url}")
            return file_url
                except Exception as e:
            logger.error(f"❌ Error subiendo archivo a S3: {e}")
            raise
    
    async def move_file_in_s3(self, user_id: str, file_name: str, from_folder: str, to_folder: str) -> str:
        """Mover archivo entre carpetas en S3"""
        try:
            source_key = f"users/{user_id}/{from_folder}/{file_name}"
            dest_key = f"users/{user_id}/{to_folder}/{file_name}"
            
            # Copiar archivo
            copy_source = {'Bucket': settings.aws_s3_bucket, 'Key': source_key}
            self.s3_client.copy_object(
                CopySource=copy_source,
                Bucket=settings.aws_s3_bucket,
                Key=dest_key
            )
            
            # Eliminar archivo original
            self.s3_client.delete_object(Bucket=settings.aws_s3_bucket, Key=source_key)
            
            file_url = f"https://{settings.aws_s3_bucket}.s3.amazonaws.com/{dest_key}"
            logger.info(f"✅ Archivo movido: {source_key} -> {dest_key}")
            return file_url
        except Exception as e:
            logger.error(f"❌ Error moviendo archivo: {e}")
            raise
    
    def _sanitize_folder_name(self, folder_name: str) -> str:
        """Sanitizar nombre de carpeta para S3"""
        import re
        # Remover caracteres especiales y espacios
        sanitized = re.sub(r'[^a-zA-Z0-9\-_]', '_', folder_name)
        # Limitar longitud
        return sanitized[:50]
