import logging
from typing import Any, Dict, List

import boto3

logger = logging.getLogger(__name__)

class ComprehendService:
    def __init__(self):
        self.comprehend_client = boto3.client('comprehend', region_name='us-east-1')
        self.custom_classifier_arn = None  # Se configurará cuando se cree el clasificador
        
    async def categorize_document(self, text: str, document_type: str = None) -> Dict[str, Any]:
        """
        Categoriza un documento usando AWS Comprehend Custom Classification
        """
        try:
            # Limitar el texto a 5000 caracteres (límite de Comprehend)
            if len(text) > 5000:
                text = text[:5000]
            
            # Detectar idioma
            language = await self._detect_language(text)
            
            # Usar Custom Classification si está disponible
            if self.custom_classifier_arn:
                classification_result = await self._classify_with_custom_model(text)
                category = classification_result['category']
                confidence = classification_result['confidence']
            else:
                # Fallback a clasificación por reglas si no hay modelo personalizado
                category, confidence = await self._classify_with_rules(text, document_type)
            
            # Detectar entidades para etiquetas adicionales
            entities = await self._detect_entities(text)
            
            # Detectar frases clave
            key_phrases = await self._detect_key_phrases(text, language)
            
            # Detectar sentimiento
            sentiment = await self._detect_sentiment(text, language)
            
            # Generar etiquetas automáticas
            tags = await self._generate_tags(text, entities, key_phrases, category)
            
            return {
                'category': category,
                'confidence': confidence,
                'tags': tags,
                'entities': entities,
                'language': language,
                'key_phrases': key_phrases,
                'sentiment': sentiment,
                'classification_method': 'custom_model' if self.custom_classifier_arn else 'rules_based'
            }
            
        except Exception as e:
            logger.error(f"Error en categorización: {str(e)}")
            raise
    
    async def _classify_with_custom_model(self, text: str) -> Dict[str, Any]:
        """Clasifica el documento usando el modelo personalizado de Comprehend"""
        try:
            response = self.comprehend_client.classify_document(
                Text=text,
                EndpointArn=self.custom_classifier_arn
            )
            
            # Obtener la clasificación con mayor confianza
            if response['Classes']:
                best_class = max(response['Classes'], key=lambda x: x['Score'])
                return {
                    'category': best_class['Name'],
                    'confidence': best_class['Score']
                }
            else:
                return {
                    'category': 'general',
                    'confidence': 0.5
                }
                
        except Exception as e:
            logger.error(f"Error en clasificación personalizada: {str(e)}")
            # Fallback a clasificación por reglas
            return await self._classify_with_rules(text)
    
    async def _classify_with_rules(self, text: str, document_type: str = None) -> tuple[str, float]:
        """Clasificación por reglas como fallback"""
        try:
            # Si ya tenemos un tipo de documento, usarlo como base
            if document_type:
                base_category = self._map_document_type_to_category(document_type)
                if base_category != 'general':
                    return base_category, 0.8
            
            # Analizar texto para determinar categoría
            text_lower = text.lower()
            
            # Categorías financieras
            financial_keywords = ['dinero', 'pago', 'cobro', 'factura', 'invoice', 'bill', 'precio', 'costo', 'total', 'subtotal', 'impuesto', 'iva']
            if any(keyword in text_lower for keyword in financial_keywords):
                return 'financiero', 0.7
            
            # Categorías legales
            legal_keywords = ['contrato', 'contract', 'acuerdo', 'agreement', 'términos', 'condiciones', 'cláusula', 'jurídico', 'legal']
            if any(keyword in text_lower for keyword in legal_keywords):
                return 'legal', 0.7
            
            # Categorías médicas
            medical_keywords = ['médico', 'doctor', 'hospital', 'clínica', 'medicina', 'medicamento', 'tratamiento', 'diagnóstico', 'paciente']
            if any(keyword in text_lower for keyword in medical_keywords):
                return 'médico', 0.7
            
            # Categorías educativas
            educational_keywords = ['estudiante', 'profesor', 'universidad', 'colegio', 'escuela', 'curso', 'materia', 'examen', 'calificación', 'diploma']
            if any(keyword in text_lower for keyword in educational_keywords):
                return 'educativo', 0.7
            
            # Categorías de identificación
            id_keywords = ['identificación', 'id', 'cedula', 'passport', 'licencia', 'carnet', 'documento de identidad']
            if any(keyword in text_lower for keyword in id_keywords):
                return 'identificación', 0.7
            
            return 'general', 0.5
            
        except Exception as e:
            logger.error(f"Error en clasificación por reglas: {str(e)}")
            return 'general', 0.3
    
    async def create_custom_classifier(self, classifier_name: str, training_data: List[Dict]) -> str:
        """Crea un clasificador personalizado de Comprehend"""
        try:
            # Preparar datos de entrenamiento
            training_documents = []
            for item in training_data:
                training_documents.append({
                    'Text': item['text'],
                    'Labels': [{'Name': item['category'], 'Score': 1.0}]
                })
            
            # Crear el clasificador
            response = self.comprehend_client.create_document_classifier(
                DocumentClassifierName=classifier_name,
                DataAccessRoleArn='arn:aws:iam::YOUR_ACCOUNT:role/ComprehendDataAccessRole',  # Necesitas crear este rol
                InputDataConfig={
                    'Documents': training_documents
                },
                LanguageCode='es'
            )
            
            classifier_arn = response['DocumentClassifierArn']
            self.custom_classifier_arn = classifier_arn
            
            logger.info(f"Clasificador creado: {classifier_arn}")
            return classifier_arn
            
        except Exception as e:
            logger.error(f"Error creando clasificador personalizado: {str(e)}")
            raise
    
    async def _detect_entities(self, text: str) -> List[Dict]:
        """Detecta entidades en el texto"""
        try:
            response = self.comprehend_client.detect_entities(
                Text=text,
                LanguageCode='es'  # Español por defecto
            )
            
            entities = []
            for entity in response.get('Entities', []):
                entities.append({
                    'text': entity['Text'],
                    'type': entity['Type'],
                    'confidence': entity['Score'],
                    'begin_offset': entity['BeginOffset'],
                    'end_offset': entity['EndOffset']
                })
            
            return entities
            
        except Exception as e:
            logger.error(f"Error detectando entidades: {str(e)}")
            return []
    
    async def _detect_sentiment(self, text: str) -> Dict:
        """Detecta el sentimiento del texto"""
        try:
            response = self.comprehend_client.detect_sentiment(
                Text=text,
                LanguageCode='es'
            )
            
            return {
                'sentiment': response['Sentiment'],
                'confidence': response['SentimentScore']
            }
            
        except Exception as e:
            logger.error(f"Error detectando sentimiento: {str(e)}")
            return {'sentiment': 'NEUTRAL', 'confidence': 0.5}
    
    async def _detect_language(self, text: str) -> str:
        """Detecta el idioma del texto"""
        try:
            response = self.comprehend_client.detect_dominant_language(Text=text)
            
            if response['Languages']:
                return response['Languages'][0]['LanguageCode']
            return 'es'
            
        except Exception as e:
            logger.error(f"Error detectando idioma: {str(e)}")
            return 'es'
    
    async def _detect_key_phrases(self, text: str, language: str) -> List[str]:
        """Detecta frases clave en el texto"""
        try:
            response = self.comprehend_client.detect_key_phrases(
                Text=text,
                LanguageCode=language
            )
            
            key_phrases = []
            for phrase in response.get('KeyPhrases', []):
                key_phrases.append({
                    'text': phrase['Text'],
                    'confidence': phrase['Score']
                })
            
            return key_phrases
            
        except Exception as e:
            logger.error(f"Error detectando frases clave: {str(e)}")
            return []
    
    
    async def _generate_tags(self, text: str, entities: List[Dict], key_phrases: List[Dict], document_type: str = None) -> List[str]:
        """Genera etiquetas automáticas para el documento"""
        try:
            tags = set()
            
            # Agregar etiquetas basadas en el tipo de documento
            if document_type:
                tags.add(document_type)
            
            # Agregar etiquetas basadas en entidades importantes
            important_entity_types = ['PERSON', 'ORGANIZATION', 'LOCATION', 'DATE', 'MONEY', 'PERCENT']
            for entity in entities:
                if entity['type'] in important_entity_types and entity['confidence'] > 0.8:
                    tags.add(entity['text'].lower())
            
            # Agregar etiquetas basadas en frases clave con alta confianza
            for phrase in key_phrases:
                if phrase['confidence'] > 0.8:
                    tags.add(phrase['text'].lower())
            
            # Agregar etiquetas basadas en palabras clave específicas
            text_lower = text.lower()
            
            # Etiquetas de urgencia
            if any(word in text_lower for word in ['urgente', 'urgent', 'inmediato', 'asap']):
                tags.add('urgente')
            
            # Etiquetas de confidencialidad
            if any(word in text_lower for word in ['confidencial', 'confidential', 'privado', 'private']):
                tags.add('confidencial')
            
            # Etiquetas de estado
            if any(word in text_lower for word in ['borrador', 'draft', 'final', 'aprobado', 'approved']):
                tags.add('borrador' if 'borrador' in text_lower or 'draft' in text_lower else 'final')
            
            # Etiquetas de formato
            if any(word in text_lower for word in ['firmado', 'signed', 'firma', 'signature']):
                tags.add('firmado')
            
            return list(tags)[:10]  # Limitar a 10 etiquetas
            
        except Exception as e:
            logger.error(f"Error generando etiquetas: {str(e)}")
            return []
    
    def _map_document_type_to_category(self, document_type: str) -> str:
        """Mapea el tipo de documento a una categoría"""
        mapping = {
            'factura': 'financiero',
            'contrato': 'legal',
            'identificación': 'identificación',
            'recibo': 'financiero',
            'certificado': 'educativo',
            'reporte': 'general'
        }
        return mapping.get(document_type, 'general')
    
    def _calculate_confidence(self, entities: List[Dict], key_phrases: List[Dict], sentiment: Dict) -> float:
        """Calcula la confianza general de la categorización"""
        try:
            if not entities and not key_phrases:
                return 0.3
            
            # Calcular confianza basada en entidades
            entity_confidence = 0
            if entities:
                entity_confidence = sum(entity['confidence'] for entity in entities) / len(entities)
            
            # Calcular confianza basada en frases clave
            phrase_confidence = 0
            if key_phrases:
                phrase_confidence = sum(phrase['confidence'] for phrase in key_phrases) / len(key_phrases)
            
            # Calcular confianza basada en sentimiento
            sentiment_confidence = sentiment.get('confidence', {}).get('Mixed', 0.5)
            
            # Promedio ponderado
            total_confidence = (entity_confidence * 0.4 + phrase_confidence * 0.4 + sentiment_confidence * 0.2)
            
            return min(max(total_confidence, 0.1), 1.0)
            
        except Exception as e:
            logger.error(f"Error calculando confianza: {str(e)}")
            return 0.5
    
    async def _detect_sentiment(self, text: str, language: str) -> Dict[str, Any]:
        """
        Detecta el sentimiento del texto usando AWS Comprehend
        """
        try:
            if len(text) < 20:  # Texto muy corto
                return {
                    'sentiment': 'NEUTRAL',
                    'confidence': {
                        'POSITIVE': 0.33,
                        'NEGATIVE': 0.33,
                        'NEUTRAL': 0.34,
                        'MIXED': 0.0
                    }
                }
            
            response = self.comprehend_client.detect_sentiment(
                Text=text,
                LanguageCode=language
            )
            
            return {
                'sentiment': response['Sentiment'],
                'confidence': {
                    'POSITIVE': response['SentimentScore']['Positive'],
                    'NEGATIVE': response['SentimentScore']['Negative'],
                    'NEUTRAL': response['SentimentScore']['Neutral'],
                    'MIXED': response['SentimentScore']['Mixed']
                }
            }
            
        except Exception as e:
            logger.error(f"Error detectando sentimiento: {str(e)}")
            return {
                'sentiment': 'NEUTRAL',
                'confidence': {
                    'POSITIVE': 0.33,
                    'NEGATIVE': 0.33,
                    'NEUTRAL': 0.34,
                    'MIXED': 0.0
                }
            }
