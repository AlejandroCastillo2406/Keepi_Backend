from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import Dict, Any
import stripe
import logging
import os
import json
from datetime import datetime

from app.config.database import get_db
from app.services.subscription_service import SubscriptionService
from app.models.subscription import (
    Subscription, SubscriptionResponse, PaymentIntentRequest, PaymentIntentResponse,
    SubscriptionPlan, SubscriptionStatus, WebhookEvent
)
from app.utils.auth import get_current_user
from app.models.user import User

# Configurar logging
logger = logging.getLogger(__name__)

# Router para suscripciones
router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])

# Configurar Stripe
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "sk_test_...")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_test_...")

@router.get("/current", response_model=SubscriptionResponse)
async def get_current_subscription(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Obtener suscripción actual del usuario"""
    try:
        subscription_service = SubscriptionService()
        subscription = await subscription_service.get_user_subscription(str(current_user.id), db)
        
        if not subscription:
            # Crear suscripción gratuita si no existe
            subscription = await subscription_service.create_free_subscription(str(current_user.id), db)
        
        return subscription
        
    except Exception as e:
        logger.error(f"Error obteniendo suscripción: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error obteniendo información de suscripción"
        )

@router.get("/limits")
async def get_analysis_limits(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Obtener límites de análisis del usuario"""
    try:
        subscription_service = SubscriptionService()
        limits = await subscription_service.check_analysis_limit(str(current_user.id), db)
        
        return {
            "can_analyze": limits["can_analyze"],
            "analysis_remaining": limits["analysis_remaining"],
            "analysis_used": limits["analysis_used"],
            "plan": limits["plan"],
            "status": limits["status"],
            "needs_subscription": limits["needs_subscription"],
            "subscription_message": "Suscríbete para obtener análisis ilimitados" if limits["needs_subscription"] else None
        }
        
    except Exception as e:
        logger.error(f"Error obteniendo límites: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error obteniendo límites de análisis"
        )

@router.post("/create-checkout-session")
async def create_checkout_session(
    request: PaymentIntentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Crear Checkout Session para redirección a Stripe"""
    try:
        subscription_service = SubscriptionService()
        
        # Validar plan
        if request.plan != SubscriptionPlan.PREMIUM:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Solo el plan Premium está disponible"
            )
        
        checkout_session = await subscription_service.create_checkout_session(
            str(current_user.id), 
            request, 
            db
        )
        
        return {
            "status": "success",
            "checkout_url": checkout_session["checkout_url"],
            "checkout_session_id": checkout_session["checkout_session_id"],
            "message": "Redirige al usuario a checkout_url para completar el pago"
        }
        
    except ValueError as e:
        logger.error(f"Error de validación: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error creando Checkout Session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error procesando el pago. Inténtalo de nuevo."
        )

@router.post("/create-payment-intent", response_model=PaymentIntentResponse)
async def create_payment_intent(
    request: PaymentIntentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Crear Payment Intent para suscripción (método alternativo)"""
    try:
        # Debug de variables de entorno
        import os
        stripe_key = os.getenv("STRIPE_SECRET_KEY")
        stripe_price = os.getenv("STRIPE_PREMIUM_PRICE_ID")
        
        logger.info(f"🔍 Debug Stripe - Secret Key: {'✅ Configurada' if stripe_key else '❌ No encontrada'}")
        logger.info(f"🔍 Debug Stripe - Price ID: {'✅ Configurada' if stripe_price else '❌ No encontrada'}")
        
        subscription_service = SubscriptionService()
        
        # Validar plan
        if request.plan != SubscriptionPlan.PREMIUM:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Solo el plan Premium está disponible"
            )
        
        payment_intent = await subscription_service.create_payment_intent(
            str(current_user.id), 
            request, 
            db
        )
        
        return payment_intent
        
    except ValueError as e:
        logger.error(f"Error de validación: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error creando Payment Intent: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error procesando el pago. Inténtalo de nuevo."
        )

@router.delete("/cancel")
async def cancel_subscription(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Cancelar suscripción del usuario"""
    try:
        subscription_service = SubscriptionService()
        success = await subscription_service.cancel_subscription(str(current_user.id), db)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No se encontró una suscripción activa para cancelar"
            )
        
        return {
            "message": "Suscripción cancelada exitosamente",
            "status": "canceled"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelando suscripción: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error cancelando suscripción"
        )

@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    db: Session = Depends(get_db)
):
    """Manejar webhooks de Stripe"""
    try:
        payload = await request.body()
        sig_header = request.headers.get('stripe-signature')
        
        # Verificar el webhook
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, STRIPE_WEBHOOK_SECRET
            )
        except ValueError as e:
            logger.error(f"Payload inválido: {e}")
            raise HTTPException(status_code=400, detail="Payload inválido")
        except stripe.error.SignatureVerificationError as e:
            logger.error(f"Firma inválida: {e}")
            raise HTTPException(status_code=400, detail="Firma inválida")
        
        # Procesar el evento
        subscription_service = SubscriptionService()
        success = await subscription_service.handle_webhook_event(event, db)
        
        if success:
            return {"received": True}
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error procesando webhook"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error en webhook: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor"
        )

@router.get("/plans")
async def get_subscription_plans():
    """Obtener información de planes de suscripción"""
    return {
        "plans": [
            {
                "id": SubscriptionPlan.FREE,
                "name": "Plan Gratuito",
                "description": "2 análisis de documentos gratuitos",
                "price": 0,
                "currency": "MXN",
                "interval": "lifetime",
                "features": [
                    "2 análisis de documentos",
                    "Almacenamiento básico",
                    "Soporte por email"
                ],
                "analysis_limit": 2,
                "recommended": False
            },
            {
                "id": SubscriptionPlan.PREMIUM,
                "name": "Plan Premium",
                "description": "Análisis ilimitados de documentos",
                "price": 49,
                "currency": "MXN", 
                "interval": "month",
                "features": [
                    "Análisis ilimitados de documentos",
                    "Almacenamiento ampliado (10GB)",
                    "Integración con Google Drive",
                    "Soporte prioritario",
                    "Análisis avanzados con IA",
                    "Exportación de datos"
                ],
                "analysis_limit": -1,  # Ilimitado
                "recommended": True
            },
        ]
    }

@router.get("/billing-history")
async def get_billing_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Obtener historial de facturación del usuario"""
    try:
        subscription_service = SubscriptionService()
        subscription = await subscription_service.get_user_subscription(str(current_user.id), db)
        
        if not subscription or not subscription.stripe_customer_id:
            return {"invoices": []}
        
        # Obtener facturas de Stripe
        invoices = stripe.Invoice.list(
            customer=subscription.stripe_customer_id,
            limit=10
        )
        
        billing_history = []
        for invoice in invoices.data:
            billing_history.append({
                "id": invoice.id,
                "amount": invoice.amount_paid / 100,  # Convertir de centavos
                "currency": invoice.currency.upper(),
                "status": invoice.status,
                "created": invoice.created,
                "description": invoice.description or "Suscripción Premium",
                "invoice_url": invoice.hosted_invoice_url,
                "pdf_url": invoice.invoice_pdf
            })
        
        return {"invoices": billing_history}
        
    except Exception as e:
        logger.error(f"Error obteniendo historial de facturación: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error obteniendo historial de facturación"
        )

@router.get("/usage-stats")
async def get_usage_statistics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Obtener estadísticas de uso del usuario"""
    try:
        subscription_service = SubscriptionService()
        
        # Obtener información de la suscripción
        subscription = await subscription_service.get_user_subscription(str(current_user.id), db)
        limits = await subscription_service.check_analysis_limit(str(current_user.id), db)
        
        # Obtener estadísticas de análisis (aquí podrías agregar más métricas)
        from app.models.ai_analysis import AIAnalysis
        total_analyses = db.query(AIAnalysis).filter(AIAnalysis.user_id == current_user.id).count()
        
        return {
            "current_period": {
                "analysis_used": limits["analysis_used"],
                "analysis_limit": subscription.analysis_limit if subscription else 2,
                "analysis_remaining": limits["analysis_remaining"]
            },
            "all_time": {
                "total_analyses": total_analyses,
                "account_created": current_user.created_at,
                "current_plan": limits["plan"]
            },
            "subscription_status": {
                "plan": limits["plan"],
                "status": limits["status"],
                "needs_upgrade": limits["needs_subscription"]
            }
        }
        
    except Exception as e:
        logger.error(f"Error obteniendo estadísticas: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error obteniendo estadísticas de uso"
        )

@router.get("/webhook-test")
async def webhook_test():
    """Test simple para verificar que el endpoint funciona"""
    return {"status": "webhook endpoint working", "timestamp": datetime.now().isoformat()}

@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    db: Session = Depends(get_db)
):
    """Webhook de Stripe para manejar eventos de suscripciones"""
    try:
        payload = await request.body()
        sig_header = request.headers.get('stripe-signature')
        
        webhook_secret = os.getenv('STRIPE_WEBHOOK_SECRET')
        if not webhook_secret:
            logger.error("❌ STRIPE_WEBHOOK_SECRET no configurado")
            raise HTTPException(status_code=400, detail="Webhook secret not configured")
        
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, webhook_secret
            )
        except ValueError as e:
            logger.error(f"❌ Invalid payload: {e}")
            raise HTTPException(status_code=400, detail="Invalid payload")
        except stripe.error.SignatureVerificationError as e:
            logger.error(f"❌ Invalid signature: {e}")
            raise HTTPException(status_code=400, detail="Invalid signature")
        
        logger.info(f"🔔 Webhook recibido: {event['type']}")
        logger.info(f"🔍 Evento completo: {event}")
        
        # Manejar diferentes tipos de eventos
        subscription_service = SubscriptionService()
        
        if event['type'] == 'checkout.session.completed':
            await handle_checkout_session_completed(event['data']['object'], subscription_service, db)
        
        elif event['type'] == 'customer.subscription.created':
            await handle_subscription_created(event['data']['object'], subscription_service, db)
        
        elif event['type'] == 'customer.subscription.updated':
            await handle_subscription_updated(event['data']['object'], subscription_service, db)
        
        elif event['type'] == 'customer.subscription.deleted':
            await handle_subscription_deleted(event['data']['object'], subscription_service, db)
        
        elif event['type'] == 'invoice.payment_succeeded':
            await handle_payment_succeeded(event['data']['object'], subscription_service, db)
        
        elif event['type'] == 'invoice.payment_failed':
            await handle_payment_failed(event['data']['object'], subscription_service, db)
        
        elif event['type'] == 'payment_method.attached':
            await handle_payment_method_attached(event['data']['object'], subscription_service, db)
        
        else:
            logger.info(f"🔔 Evento no manejado: {event['type']}")
            logger.info(f"🔍 Datos del evento: {event['data']}")
        
        return {"status": "success"}
        
    except Exception as e:
        logger.error(f"❌ Error procesando webhook: {e}")
        raise HTTPException(
            status_code=500,
            detail="Error procesando webhook"
        )

async def handle_checkout_session_completed(session_data: Dict[str, Any], service: SubscriptionService, db: Session):
    """Manejar completación de checkout session - EVENTO MÁS IMPORTANTE"""
    try:
        session_id = session_data['id']
        customer_id = session_data.get('customer')
        subscription_id = session_data.get('subscription')
        
        logger.info(f"🎉 Checkout Session completado: {session_id}")
        logger.info(f"🔍 Customer: {customer_id}, Subscription: {subscription_id}")
        
        if not customer_id:
            logger.error(f"❌ Checkout session sin customer_id: {session_id}")
            return
        
        # Buscar la suscripción en nuestra BD por stripe_customer_id
        subscription = db.query(Subscription).filter(
            Subscription.stripe_customer_id == customer_id
        ).first()
        
        if subscription:
            if subscription_id:
                # Actualizar con los datos de la suscripción
                subscription.stripe_subscription_id = subscription_id
                subscription.plan = SubscriptionPlan.PREMIUM
                subscription.status = SubscriptionStatus.ACTIVE
                subscription.analysis_limit = 999999  # Ilimitado para premium
                subscription.analysis_used = 0  # Resetear análisis usados
                
                # Obtener detalles de la suscripción de Stripe
                try:
                    stripe_sub = stripe.Subscription.retrieve(subscription_id)
                    subscription.current_period_start = datetime.fromtimestamp(stripe_sub.current_period_start)
                    subscription.current_period_end = datetime.fromtimestamp(stripe_sub.current_period_end)
                    logger.info(f"📅 Período: {subscription.current_period_start} - {subscription.current_period_end}")
                except Exception as e:
                    logger.warning(f"No se pudieron obtener detalles de suscripción: {e}")
                
                db.commit()
                logger.info(f"✅ Suscripción actualizada a Premium: {subscription.id}")
                logger.info(f"🎯 Análisis: {subscription.analysis_used}/{subscription.analysis_limit}")
            else:
                logger.warning(f"⚠️ Checkout session sin subscription_id: {session_id}")
        else:
            logger.error(f"❌ No se encontró suscripción para customer: {customer_id}")
            
    except Exception as e:
        logger.error(f"❌ Error procesando checkout_session_completed: {e}")
        db.rollback()

async def handle_subscription_created(subscription_data: Dict[str, Any], service: SubscriptionService, db: Session):
    """Manejar creación de suscripción"""
    try:
        stripe_subscription_id = subscription_data['id']
        stripe_customer_id = subscription_data['customer']
        status = subscription_data['status']
        
        logger.info(f"✅ Suscripción creada: {stripe_subscription_id} para customer: {stripe_customer_id}")
        
        # Buscar la suscripción en nuestra BD por stripe_customer_id
        subscription = db.query(Subscription).filter(
            Subscription.stripe_customer_id == stripe_customer_id
        ).first()
        
        if subscription:
            # Actualizar con los datos de Stripe
            subscription.stripe_subscription_id = stripe_subscription_id
            subscription.status = SubscriptionStatus.ACTIVE if status == 'active' else SubscriptionStatus.INACTIVE
            subscription.plan = SubscriptionPlan.PREMIUM  # Asumimos que es premium
            subscription.analysis_limit = 999999  # Ilimitado para premium
            subscription.current_period_start = datetime.fromtimestamp(subscription_data.get('current_period_start', 0))
            subscription.current_period_end = datetime.fromtimestamp(subscription_data.get('current_period_end', 0))
            
            db.commit()
            logger.info(f"✅ Suscripción actualizada en BD: {subscription.id}")
        else:
            logger.warning(f"⚠️ No se encontró suscripción para customer: {stripe_customer_id}")
            
    except Exception as e:
        logger.error(f"❌ Error procesando subscription_created: {e}")
        db.rollback()

async def handle_subscription_updated(subscription_data: Dict[str, Any], service: SubscriptionService, db: Session):
    """Manejar actualización de suscripción"""
    try:
        stripe_subscription_id = subscription_data['id']
        status = subscription_data['status']
        
        logger.info(f"🔄 Suscripción actualizada: {stripe_subscription_id} - status: {status}")
        
        # Buscar la suscripción en nuestra BD
        subscription = db.query(Subscription).filter(
            Subscription.stripe_subscription_id == stripe_subscription_id
        ).first()
        
        if subscription:
            # Actualizar status
            if status == 'active':
                subscription.status = SubscriptionStatus.ACTIVE
            elif status == 'canceled':
                subscription.status = SubscriptionStatus.CANCELED
                subscription.canceled_at = datetime.utcnow()
            else:
                subscription.status = SubscriptionStatus.INACTIVE
            
            subscription.current_period_start = datetime.fromtimestamp(subscription_data.get('current_period_start', 0))
            subscription.current_period_end = datetime.fromtimestamp(subscription_data.get('current_period_end', 0))
            
            db.commit()
            logger.info(f"✅ Suscripción actualizada en BD: {subscription.id}")
        else:
            logger.warning(f"⚠️ No se encontró suscripción: {stripe_subscription_id}")
            
    except Exception as e:
        logger.error(f"❌ Error procesando subscription_updated: {e}")
        db.rollback()

async def handle_subscription_deleted(subscription_data: Dict[str, Any], service: SubscriptionService, db: Session):
    """Manejar cancelación de suscripción"""
    try:
        stripe_subscription_id = subscription_data['id']
        
        logger.info(f"❌ Suscripción cancelada: {stripe_subscription_id}")
        
        # Buscar la suscripción en nuestra BD
        subscription = db.query(Subscription).filter(
            Subscription.stripe_subscription_id == stripe_subscription_id
        ).first()
        
        if subscription:
            # Cambiar a plan gratuito
            subscription.status = SubscriptionStatus.CANCELED
            subscription.plan = SubscriptionPlan.FREE
            subscription.analysis_limit = 2  # Volver al límite gratuito
            subscription.canceled_at = datetime.utcnow()
            
            db.commit()
            logger.info(f"✅ Suscripción cancelada en BD: {subscription.id}")
        else:
            logger.warning(f"⚠️ No se encontró suscripción: {stripe_subscription_id}")
            
    except Exception as e:
        logger.error(f"❌ Error procesando subscription_deleted: {e}")
        db.rollback()

async def handle_payment_succeeded(invoice_data: Dict[str, Any], service: SubscriptionService, db: Session):
    """Manejar pago exitoso"""
    try:
        invoice_id = invoice_data['id']
        subscription_id = invoice_data.get('subscription')
        
        logger.info(f"💰 Pago exitoso: {invoice_id} para suscripción: {subscription_id}")
        
        if subscription_id:
            # Buscar la suscripción en nuestra BD
            subscription = db.query(Subscription).filter(
                Subscription.stripe_subscription_id == subscription_id
            ).first()
            
            if subscription:
                # Asegurar que esté activa
                subscription.status = SubscriptionStatus.ACTIVE
                db.commit()
                logger.info(f"✅ Pago confirmado para suscripción: {subscription.id}")
            else:
                logger.warning(f"⚠️ No se encontró suscripción: {subscription_id}")
                
    except Exception as e:
        logger.error(f"❌ Error procesando payment_succeeded: {e}")
        db.rollback()

async def handle_payment_failed(invoice_data: Dict[str, Any], service: SubscriptionService, db: Session):
    """Manejar pago fallido"""
    try:
        invoice_id = invoice_data['id']
        subscription_id = invoice_data.get('subscription')
        
        logger.info(f"❌ Pago fallido: {invoice_id} para suscripción: {subscription_id}")
        
        if subscription_id:
            # Buscar la suscripción en nuestra BD
            subscription = db.query(Subscription).filter(
                Subscription.stripe_subscription_id == subscription_id
            ).first()
            
            if subscription:
                # Marcar como inactiva por falta de pago
                subscription.status = SubscriptionStatus.INACTIVE
                db.commit()
                logger.info(f"⚠️ Suscripción inactiva por pago fallido: {subscription.id}")
            else:
                logger.warning(f"⚠️ No se encontró suscripción: {subscription_id}")
                
    except Exception as e:
        logger.error(f"❌ Error procesando payment_failed: {e}")
        db.rollback()

async def handle_payment_method_attached(payment_method_data: Dict[str, Any], service: SubscriptionService, db: Session):
    """Manejar payment method attached - evento que está llegando"""
    try:
        payment_method_id = payment_method_data['id']
        customer_id = payment_method_data.get('customer')
        
        logger.info(f"💳 Payment Method attached: {payment_method_id}")
        logger.info(f"🔍 Customer: {customer_id}")
        
        if customer_id:
            # Buscar la suscripción en nuestra BD
            subscription = db.query(Subscription).filter(
                Subscription.stripe_customer_id == customer_id
            ).first()
            
            if subscription:
                logger.info(f"✅ Suscripción encontrada para customer: {customer_id}")
                logger.info(f"🔍 Plan actual: {subscription.plan}, Status: {subscription.status}")
                
                # Si el plan es FREE, intentar actualizar a PREMIUM
                if subscription.plan == SubscriptionPlan.FREE:
                    logger.info("🔄 Intentando actualizar suscripción a Premium...")
                    
                    # Verificar si hay una suscripción activa en Stripe
                    try:
                        import stripe
                        stripe_subscriptions = stripe.Subscription.list(customer=customer_id, status='active')
                        
                        if stripe_subscriptions.data:
                            stripe_sub = stripe_subscriptions.data[0]
                            subscription.stripe_subscription_id = stripe_sub.id
                            subscription.plan = SubscriptionPlan.PREMIUM
                            subscription.status = SubscriptionStatus.ACTIVE
                            subscription.analysis_limit = 999999
                            subscription.analysis_used = 0
                            
                            db.commit()
                            logger.info(f"✅ Suscripción actualizada a Premium: {subscription.id}")
                        else:
                            logger.warning("⚠️ No hay suscripciones activas en Stripe")
                            
                    except Exception as e:
                        logger.error(f"❌ Error verificando suscripciones en Stripe: {e}")
                else:
                    logger.info(f"ℹ️ Suscripción ya es {subscription.plan}")
            else:
                logger.warning(f"⚠️ No se encontró suscripción para customer: {customer_id}")
                
    except Exception as e:
        logger.error(f"❌ Error procesando payment_method_attached: {e}")
        db.rollback()

