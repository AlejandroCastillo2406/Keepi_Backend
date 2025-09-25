from typing import Optional, Dict, Any
import stripe
import logging
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from app.models.subscription import (
    Subscription, SubscriptionCreate, SubscriptionUpdate, SubscriptionResponse,
    SubscriptionStatus, SubscriptionPlan, PaymentIntentRequest, PaymentIntentResponse
)
from app.models.user import User
from app.config.database import get_db
import os

# Configurar logging
logger = logging.getLogger(__name__)

# Configurar Stripe
stripe_secret_key = os.getenv("STRIPE_SECRET_KEY")
if not stripe_secret_key:
    logger.error("❌ STRIPE_SECRET_KEY no encontrada en variables de entorno")
    logger.error("Variables disponibles: " + str(list(os.environ.keys())))
else:
    logger.info(f"✅ STRIPE_SECRET_KEY configurada: {stripe_secret_key[:10]}...")

stripe.api_key = stripe_secret_key

class SubscriptionService:
    """Servicio para manejo de suscripciones y pagos con Stripe"""
    
    # Precios de Stripe (estos deben configurarse en Stripe Dashboard)
    STRIPE_PRICES = {
        SubscriptionPlan.PREMIUM: os.getenv("STRIPE_PREMIUM_PRICE_ID", "price_premium_test")
        # Solo Premium - Enterprise removido
    }
    
    def __init__(self):
        self.stripe = stripe
    
    async def get_user_subscription(self, user_id: str, db: Session) -> Optional[SubscriptionResponse]:
        """Obtener suscripción del usuario"""
        try:
            subscription = db.query(Subscription).filter(Subscription.user_id == user_id).first()
            if subscription:
                return SubscriptionResponse.from_orm(subscription)
            return None
        except Exception as e:
            logger.error(f"Error obteniendo suscripción del usuario {user_id}: {e}")
            return None
    
    async def create_free_subscription(self, user_id: str, db: Session) -> SubscriptionResponse:
        """Crear suscripción gratuita para nuevo usuario"""
        try:
            # Verificar si ya existe
            existing = db.query(Subscription).filter(Subscription.user_id == user_id).first()
            if existing:
                return SubscriptionResponse.from_orm(existing)
            
            # Crear suscripción gratuita
            subscription_data = SubscriptionCreate(
                user_id=user_id,
                plan=SubscriptionPlan.FREE,
                analysis_limit=2
            )
            
            subscription = Subscription(
                user_id=user_id,
                plan=subscription_data.plan,
                status=SubscriptionStatus.ACTIVE,  # Plan gratuito está activo por defecto
                analysis_limit=subscription_data.analysis_limit,
                analysis_used=0
            )
            
            db.add(subscription)
            db.commit()
            db.refresh(subscription)
            
            logger.info(f"✅ Suscripción gratuita creada para usuario {user_id}")
            return SubscriptionResponse.from_orm(subscription)
            
        except Exception as e:
            logger.error(f"Error creando suscripción gratuita: {e}")
            db.rollback()
            raise
    
    async def create_stripe_customer(self, user: User) -> str:
        """Crear cliente en Stripe"""
        try:
            # Verificar que stripe.api_key esté configurado
            if not stripe.api_key:
                logger.error("❌ stripe.api_key no está configurado")
                # Intentar configurar nuevamente
                stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
                if not stripe.api_key:
                    raise ValueError("STRIPE_SECRET_KEY no encontrada")
            
            logger.info(f"🔍 Creando cliente Stripe para {user.email}")
            logger.info(f"🔍 User data - email: {user.email}, name: {user.name}, id: {user.id}")
            
            # Preparar datos del cliente
            customer_data = {
                'email': user.email,
                'metadata': {
                    'user_id': str(user.id)
                }
            }
            
            # Solo agregar name si no es None
            if user.name:
                customer_data['name'] = user.name
            
            logger.info(f"🔍 Customer data: {customer_data}")
            
            # Debug de la configuración de Stripe antes de la llamada
            logger.info(f"🔍 Stripe API Key configurada: {bool(stripe.api_key)}")
            logger.info(f"🔍 Stripe API Key tipo: {type(stripe.api_key)}")
            logger.info(f"🔍 Stripe API Key valor: {stripe.api_key[:10] if stripe.api_key else 'None'}...")
            
            # Verificar la configuración de Stripe
            logger.info(f"🔍 Stripe version: {stripe.__version__}")
            logger.info(f"🔍 Stripe API base: {stripe.api_base}")
            logger.info(f"🔍 Stripe API version: {stripe.api_version}")
            
            try:
                logger.info(f"🔍 Llamando a stripe.Customer.create con: {customer_data}")
                customer = stripe.Customer.create(**customer_data)
                logger.info(f"🔍 Respuesta de Stripe: {customer}")
                logger.info(f"🔍 Tipo de respuesta: {type(customer)}")
            except Exception as stripe_error:
                logger.error(f"❌ Error en stripe.Customer.create: {stripe_error}")
                logger.error(f"❌ Tipo de error: {type(stripe_error).__name__}")
                logger.error(f"❌ Detalles: {str(stripe_error)}")
                logger.error(f"❌ Traceback completo: {stripe_error.__traceback__}")
                raise
            
            # Debug detallado del objeto customer
            logger.info(f"🔍 Customer object: {customer}")
            logger.info(f"🔍 Customer object type: {type(customer)}")
            logger.info(f"🔍 Customer is None: {customer is None}")
            
            if customer is None:
                logger.error("❌ Stripe retornó None - esto no debería pasar")
                raise ValueError("Stripe retornó None en lugar de un objeto Customer")
            
            logger.info(f"🔍 Customer attributes: {dir(customer)}")
            logger.info(f"🔍 Customer id: {getattr(customer, 'id', 'NO_ID')}")
            
            # Verificar que el objeto tenga el atributo id
            if not hasattr(customer, 'id'):
                logger.error("❌ El objeto Customer no tiene atributo 'id'")
                logger.error(f"Atributos disponibles: {dir(customer)}")
                raise ValueError("El objeto Customer no tiene atributo 'id'")
            
            logger.info(f"✅ Cliente Stripe creado: {customer.id} para usuario {user.id}")
            return customer.id
            
        except Exception as e:
            logger.error(f"Error creando cliente Stripe: {e}")
            logger.error(f"stripe.api_key configurado: {bool(stripe.api_key)}")
            logger.error(f"Tipo de error: {type(e).__name__}")
            logger.error(f"Detalles del error: {str(e)}")
            
            # Si es un error de Stripe, mostrar más detalles
            if hasattr(e, 'user_message'):
                logger.error(f"Mensaje de usuario: {e.user_message}")
            if hasattr(e, 'code'):
                logger.error(f"Código de error: {e.code}")
                
            raise
    
    async def create_payment_intent(
        self, 
        user_id: str, 
        request: PaymentIntentRequest, 
        db: Session
    ) -> PaymentIntentResponse:
        """Crear Payment Intent para suscripción"""
        try:
            # Obtener usuario
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                raise ValueError("Usuario no encontrado")
            
            # Obtener o crear suscripción
            subscription = db.query(Subscription).filter(Subscription.user_id == user_id).first()
            if not subscription:
                subscription = await self.create_free_subscription(user_id, db)
            
            # Obtener o crear cliente Stripe
            if not subscription.stripe_customer_id:
                customer_id = await self.create_stripe_customer(user)
                subscription.stripe_customer_id = customer_id
                db.commit()
            
            # Obtener precio según el plan
            price_id = self.STRIPE_PRICES.get(request.plan)
            if not price_id:
                raise ValueError(f"Plan {request.plan} no válido")
            
            logger.info(f"🔍 Creando suscripción Stripe con price_id: {price_id}")
            
            # Verificar stripe.api_key antes de crear suscripción
            if not stripe.api_key:
                logger.error("❌ stripe.api_key no configurado antes de crear suscripción")
                stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
            
            # Crear suscripción en Stripe
            stripe_subscription = stripe.Subscription.create(
                customer=subscription.stripe_customer_id,
                items=[{'price': price_id}],
                payment_behavior='default_incomplete',
                payment_settings={'save_default_payment_method': 'on_subscription'},
                expand=['latest_invoice.payment_intent'],
                metadata={
                    'user_id': str(user_id),
                    'plan': request.plan
                }
            )
            
            # Actualizar suscripción local
            subscription.stripe_subscription_id = stripe_subscription.id
            subscription.stripe_price_id = price_id
            subscription.plan = request.plan
            subscription.status = SubscriptionStatus.INACTIVE  # Se activará con webhook
            subscription.current_period_start = datetime.fromtimestamp(stripe_subscription.current_period_start)
            subscription.current_period_end = datetime.fromtimestamp(stripe_subscription.current_period_end)
            
            # Si es premium, análisis ilimitados
            if request.plan == SubscriptionPlan.PREMIUM:
                subscription.analysis_limit = 999999
            
            db.commit()
            
            payment_intent = stripe_subscription.latest_invoice.payment_intent
            
            logger.info(f"✅ Payment Intent creado: {payment_intent.id} para usuario {user_id}")
            
            return PaymentIntentResponse(
                client_secret=payment_intent.client_secret,
                status=payment_intent.status,
                subscription_id=stripe_subscription.id
            )
            
        except Exception as e:
            logger.error(f"Error creando Payment Intent: {e}")
            db.rollback()
            raise
    
    async def handle_webhook_event(self, event_data: Dict[str, Any], db: Session) -> bool:
        """Manejar eventos de webhook de Stripe"""
        try:
            event_type = event_data.get('type')
            data_object = event_data.get('data', {}).get('object', {})
            
            logger.info(f"📥 Webhook recibido: {event_type}")
            
            if event_type == 'customer.subscription.created':
                await self._handle_subscription_created(data_object, db)
            elif event_type == 'customer.subscription.updated':
                await self._handle_subscription_updated(data_object, db)
            elif event_type == 'customer.subscription.deleted':
                await self._handle_subscription_deleted(data_object, db)
            elif event_type == 'invoice.payment_succeeded':
                await self._handle_payment_succeeded(data_object, db)
            elif event_type == 'invoice.payment_failed':
                await self._handle_payment_failed(data_object, db)
            else:
                logger.info(f"⚠️ Evento webhook no manejado: {event_type}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error manejando webhook: {e}")
            return False
    
    async def _handle_subscription_created(self, data: Dict[str, Any], db: Session):
        """Manejar creación de suscripción"""
        stripe_subscription_id = data.get('id')
        user_id = data.get('metadata', {}).get('user_id')
        
        if not user_id:
            logger.error("No se encontró user_id en metadata de suscripción")
            return
        
        subscription = db.query(Subscription).filter(
            Subscription.stripe_subscription_id == stripe_subscription_id
        ).first()
        
        if subscription:
            subscription.status = SubscriptionStatus.ACTIVE
            subscription.current_period_start = datetime.fromtimestamp(data.get('current_period_start'))
            subscription.current_period_end = datetime.fromtimestamp(data.get('current_period_end'))
            db.commit()
            logger.info(f"✅ Suscripción activada: {stripe_subscription_id}")
    
    async def _handle_subscription_updated(self, data: Dict[str, Any], db: Session):
        """Manejar actualización de suscripción"""
        stripe_subscription_id = data.get('id')
        status = data.get('status')
        
        subscription = db.query(Subscription).filter(
            Subscription.stripe_subscription_id == stripe_subscription_id
        ).first()
        
        if subscription:
            # Mapear estados de Stripe a nuestros estados
            status_mapping = {
                'active': SubscriptionStatus.ACTIVE,
                'canceled': SubscriptionStatus.CANCELED,
                'past_due': SubscriptionStatus.PAST_DUE,
                'trialing': SubscriptionStatus.TRIALING,
                'incomplete': SubscriptionStatus.INACTIVE,
                'incomplete_expired': SubscriptionStatus.INACTIVE
            }
            
            subscription.status = status_mapping.get(status, SubscriptionStatus.INACTIVE)
            subscription.current_period_start = datetime.fromtimestamp(data.get('current_period_start'))
            subscription.current_period_end = datetime.fromtimestamp(data.get('current_period_end'))
            
            if status == 'canceled':
                subscription.canceled_at = datetime.utcnow()
                # Volver a plan gratuito
                subscription.plan = SubscriptionPlan.FREE
                subscription.analysis_limit = 2
            
            db.commit()
            logger.info(f"✅ Suscripción actualizada: {stripe_subscription_id} - Status: {status}")
    
    async def _handle_subscription_deleted(self, data: Dict[str, Any], db: Session):
        """Manejar cancelación de suscripción"""
        stripe_subscription_id = data.get('id')
        
        subscription = db.query(Subscription).filter(
            Subscription.stripe_subscription_id == stripe_subscription_id
        ).first()
        
        if subscription:
            subscription.status = SubscriptionStatus.CANCELED
            subscription.canceled_at = datetime.utcnow()
            subscription.plan = SubscriptionPlan.FREE
            subscription.analysis_limit = 2
            db.commit()
            logger.info(f"✅ Suscripción cancelada: {stripe_subscription_id}")
    
    async def _handle_payment_succeeded(self, data: Dict[str, Any], db: Session):
        """Manejar pago exitoso"""
        subscription_id = data.get('subscription')
        
        if subscription_id:
            subscription = db.query(Subscription).filter(
                Subscription.stripe_subscription_id == subscription_id
            ).first()
            
            if subscription:
                subscription.status = SubscriptionStatus.ACTIVE
                db.commit()
                logger.info(f"✅ Pago exitoso para suscripción: {subscription_id}")
    
    async def _handle_payment_failed(self, data: Dict[str, Any], db: Session):
        """Manejar pago fallido"""
        subscription_id = data.get('subscription')
        
        if subscription_id:
            subscription = db.query(Subscription).filter(
                Subscription.stripe_subscription_id == subscription_id
            ).first()
            
            if subscription:
                subscription.status = SubscriptionStatus.PAST_DUE
                db.commit()
                logger.info(f"⚠️ Pago fallido para suscripción: {subscription_id}")
    
    async def cancel_subscription(self, user_id: str, db: Session) -> bool:
        """Cancelar suscripción del usuario"""
        try:
            subscription = db.query(Subscription).filter(Subscription.user_id == user_id).first()
            
            if not subscription or not subscription.stripe_subscription_id:
                logger.error(f"No se encontró suscripción activa para usuario {user_id}")
                return False
            
            # Cancelar en Stripe
            stripe.Subscription.delete(subscription.stripe_subscription_id)
            
            # Actualizar localmente
            subscription.status = SubscriptionStatus.CANCELED
            subscription.canceled_at = datetime.utcnow()
            subscription.plan = SubscriptionPlan.FREE
            subscription.analysis_limit = 2
            
            db.commit()
            
            logger.info(f"✅ Suscripción cancelada para usuario {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error cancelando suscripción: {e}")
            db.rollback()
            return False
    
    async def check_analysis_limit(self, user_id: str, db: Session) -> Dict[str, Any]:
        """Verificar límite de análisis del usuario"""
        try:
            subscription = db.query(Subscription).filter(Subscription.user_id == user_id).first()
            
            if not subscription:
                # Crear suscripción gratuita si no existe
                subscription = await self.create_free_subscription(user_id, db)
            
            can_analyze = subscription.has_analysis_remaining
            remaining = subscription.analysis_remaining
            
            return {
                "can_analyze": can_analyze,
                "analysis_remaining": remaining,
                "analysis_used": subscription.analysis_used,
                "plan": subscription.plan,
                "status": subscription.status,
                "needs_subscription": not can_analyze and subscription.plan == SubscriptionPlan.FREE
            }
            
        except Exception as e:
            logger.error(f"Error verificando límite de análisis: {e}")
            return {
                "can_analyze": False,
                "analysis_remaining": 0,
                "analysis_used": 0,
                "plan": SubscriptionPlan.FREE,
                "status": SubscriptionStatus.INACTIVE,
                "needs_subscription": True
            }
    
    async def increment_analysis_usage(self, user_id: str, db: Session) -> bool:
        """Incrementar contador de análisis usado"""
        try:
            subscription = db.query(Subscription).filter(Subscription.user_id == user_id).first()
            
            if not subscription:
                logger.error(f"No se encontró suscripción para usuario {user_id}")
                return False
            
            # Solo incrementar para plan gratuito
            if subscription.plan == SubscriptionPlan.FREE:
                subscription.analysis_used += 1
                db.commit()
                logger.info(f"✅ Análisis usado incrementado para usuario {user_id}: {subscription.analysis_used}/{subscription.analysis_limit}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error incrementando uso de análisis: {e}")
            db.rollback()
            return False
