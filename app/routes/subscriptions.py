"""
Rutas de suscripciones: endpoints y webhook de Stripe.
Orquestación mínima; lógica en SubscriptionService.
"""
import logging
from datetime import datetime

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.config import settings
from app.models.subscription import (
    SubscriptionPlan,
    SubscriptionResponse,
    PaymentIntentRequest,
    PaymentIntentResponse,
)
from app.models.user import User
from app.routes.dependencies import get_subscription_service
from app.services.subscription import SubscriptionService
from app.core.security import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


def _webhook_secret() -> str:
    secret = settings.stripe_webhook_secret
    if not secret:
        raise ValueError("STRIPE_WEBHOOK_SECRET no configurado")
    return secret


@router.get("/current", response_model=SubscriptionResponse)
async def get_current_subscription(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    service: SubscriptionService = Depends(get_subscription_service),
):
    """Obtener suscripción actual del usuario."""
    try:
        subscription = await service.get_user_subscription(str(current_user.id), db)
        if not subscription:
            subscription = await service.create_free_subscription(str(current_user.id), db)
        return subscription
    except Exception as e:
        logger.exception("Error obteniendo suscripción")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error obteniendo información de suscripción",
        ) from e


@router.get("/limits")
async def get_analysis_limits(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    service: SubscriptionService = Depends(get_subscription_service),
):
    """Obtener límites de análisis del usuario."""
    try:
        limits = await service.check_analysis_limit(str(current_user.id), db)
        return {
            "can_analyze": limits["can_analyze"],
            "analysis_remaining": limits["analysis_remaining"],
            "analysis_used": limits["analysis_used"],
            "plan": limits["plan"],
            "status": limits["status"],
            "needs_subscription": limits["needs_subscription"],
            "subscription_message": (
                "Suscríbete para obtener análisis ilimitados" if limits["needs_subscription"] else None
            ),
        }
    except Exception as e:
        logger.exception("Error obteniendo límites")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error obteniendo límites de análisis",
        ) from e


@router.post("/create-checkout-session")
async def create_checkout_session(
    request: PaymentIntentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    service: SubscriptionService = Depends(get_subscription_service),
):
    """Crear Checkout Session para redirección a Stripe."""
    if request.plan != SubscriptionPlan.PREMIUM:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Solo el plan Premium está disponible",
        )
    try:
        result = await service.create_checkout_session(str(current_user.id), request, db)
        return {
            "status": "success",
            "checkout_url": result["checkout_url"],
            "checkout_session_id": result["checkout_session_id"],
            "message": "Redirige al usuario a checkout_url para completar el pago",
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except Exception as e:
        logger.exception("Error creando Checkout Session")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error procesando el pago. Inténtalo de nuevo.",
        ) from e


@router.post("/create-payment-intent", response_model=PaymentIntentResponse)
async def create_payment_intent(
    request: PaymentIntentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    service: SubscriptionService = Depends(get_subscription_service),
):
    """Crear Payment Intent para suscripción (flujo alternativo)."""
    if request.plan != SubscriptionPlan.PREMIUM:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Solo el plan Premium está disponible",
        )
    try:
        return await service.create_payment_intent(str(current_user.id), request, db)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except Exception as e:
        logger.exception("Error creando Payment Intent")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error procesando el pago. Inténtalo de nuevo.",
        ) from e


@router.delete("/cancel")
async def cancel_subscription(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    service: SubscriptionService = Depends(get_subscription_service),
):
    """Cancelar suscripción del usuario."""
    try:
        success = await service.cancel_subscription(str(current_user.id), db)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No se encontró una suscripción activa para cancelar",
            )
        return {"message": "Suscripción cancelada exitosamente", "status": "canceled"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error cancelando suscripción")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error cancelando suscripción",
        ) from e


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    db: Session = Depends(get_db),
    service: SubscriptionService = Depends(get_subscription_service),
):
    """Recibe webhooks de Stripe (suscripciones y pagos)."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    try:
        secret = _webhook_secret()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, secret)
    except ValueError as e:
        logger.warning("Webhook payload inválido: %s", e)
        raise HTTPException(status_code=400, detail="Payload inválido") from e
    except stripe.error.SignatureVerificationError as e:
        logger.warning("Webhook firma inválida: %s", e)
        raise HTTPException(status_code=400, detail="Firma inválida") from e

    success = await service.handle_webhook_event(event, db)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error procesando webhook",
        )
    return {"received": True}


@router.get("/plans")
async def get_subscription_plans():
    """Información de planes de suscripción."""
    return {
        "plans": [
            {
                "id": SubscriptionPlan.FREE,
                "name": "Plan Gratuito",
                "description": "2 análisis de documentos gratuitos",
                "price": 0,
                "currency": "MXN",
                "interval": "lifetime",
                "features": ["2 análisis de documentos", "Almacenamiento básico", "Soporte por email"],
                "analysis_limit": 2,
                "recommended": False,
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
                    "Exportación de datos",
                ],
                "analysis_limit": -1,
                "recommended": True,
            },
        ]
    }


@router.get("/billing-history")
async def get_billing_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    service: SubscriptionService = Depends(get_subscription_service),
):
    """Historial de facturación del usuario (Stripe)."""
    try:
        subscription = await service.get_user_subscription(str(current_user.id), db)
        if not subscription or not subscription.stripe_customer_id:
            return {"invoices": []}
        if not settings.stripe_secret_key:
            return {"invoices": []}
        invoices = stripe.Invoice.list(customer=subscription.stripe_customer_id, limit=10)
        return {
            "invoices": [
                {
                    "id": inv.id,
                    "amount": inv.amount_paid / 100,
                    "currency": (inv.currency or "").upper(),
                    "status": inv.status,
                    "created": inv.created,
                    "description": inv.description or "Suscripción Premium",
                    "invoice_url": inv.hosted_invoice_url,
                    "pdf_url": inv.invoice_pdf,
                }
                for inv in invoices.data
            ]
        }
    except Exception as e:
        logger.exception("Error obteniendo historial de facturación")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error obteniendo historial de facturación",
        ) from e


@router.get("/usage-stats")
async def get_usage_statistics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    service: SubscriptionService = Depends(get_subscription_service),
):
    """Estadísticas de uso del usuario."""
    try:
        subscription = await service.get_user_subscription(str(current_user.id), db)
        limits = await service.check_analysis_limit(str(current_user.id), db)
        return {
            "current_period": {
                "analysis_used": limits["analysis_used"],
                "analysis_limit": subscription.analysis_limit if subscription else 2,
                "analysis_remaining": limits["analysis_remaining"],
            },
            "all_time": {
                "total_analyses": limits.get("analysis_used", 0),
                "account_created": current_user.created_at,
                "current_plan": limits["plan"],
            },
            "subscription_status": {
                "plan": limits["plan"],
                "status": limits["status"],
                "needs_upgrade": limits["needs_subscription"],
            },
        }
    except Exception as e:
        logger.exception("Error obteniendo estadísticas")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error obteniendo estadísticas de uso",
        ) from e


@router.get("/webhook-test")
async def webhook_test():
    """Comprueba que el endpoint de webhook responde."""
    return {"status": "webhook endpoint working", "timestamp": datetime.now().isoformat()}
