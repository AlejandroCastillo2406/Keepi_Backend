from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import Dict, Any
import stripe
import logging
import os
import json

from app.config.database import get_db
from app.services.subscription_service import SubscriptionService
from app.models.subscription import (
    SubscriptionResponse, PaymentIntentRequest, PaymentIntentResponse,
    SubscriptionPlan, WebhookEvent
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

@router.post("/create-payment-intent", response_model=PaymentIntentResponse)
async def create_payment_intent(
    request: PaymentIntentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Crear Payment Intent para suscripción"""
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
                "currency": "USD",
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
                "price": 9.99,
                "currency": "USD", 
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
