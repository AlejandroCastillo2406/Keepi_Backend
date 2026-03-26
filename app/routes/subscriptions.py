import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

# Importa tus dependencias de base de datos y seguridad
from app.core.database import get_db
# NOTA: Ajusta la importación de 'get_current_user' según cómo lo tengas en tu proyecto original
# (puede ser desde app.api.dependencies, app.core.security, etc.)
from app.core.security import get_current_user 

from app.models.user import User
from app.models.subscription import (
    PaymentIntentRequest,
    PaymentIntentResponse,
    SubscriptionResponse,
)
from app.models.plans import Plan, PlanResponse
from app.services.subscription.subscription_service import SubscriptionService

router = APIRouter(prefix="/subscriptions", tags=["Subscriptions"])
logger = logging.getLogger(__name__)

def get_subscription_service() -> SubscriptionService:
    return SubscriptionService()

# ============================================================
# 1. ENDPOINT DE PLANES 
# ============================================================
@router.get("/plans", response_model=List[PlanResponse])
async def get_available_plans(db: Session = Depends(get_db)):
    """
    Obtiene la lista de planes activos directamente desde la base de datos.
    Si en el futuro agregas un plan, aparecerá aquí automáticamente.
    """
    plans = db.query(Plan).filter(Plan.is_active == True).order_by(Plan.price.asc()).all()
    return [PlanResponse.from_orm(plan) for plan in plans]

# ============================================================
# 2. ENDPOINTS DE LA SUSCRIPCIÓN DEL USUARIO
# ============================================================

@router.get("/me", response_model=SubscriptionResponse)
async def get_my_subscription(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    service: SubscriptionService = Depends(get_subscription_service)
):
    """Obtiene la suscripción actual del usuario."""
    sub = await service.get_user_subscription(str(current_user.id), db)
    if not sub:
        # Si no tiene suscripción en base de datos, le asignamos el plan free por defecto
        sub = await service.create_free_subscription(str(current_user.id), db)
    return sub

@router.get("/check-analysis-limit")
async def check_analysis_limit(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    service: SubscriptionService = Depends(get_subscription_service)
):
    """Verifica si el usuario aún tiene análisis disponibles en su plan actual."""
    return await service.check_analysis_limit(str(current_user.id), db)

@router.get("/usage-stats")
async def usage_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    service: SubscriptionService = Depends(get_subscription_service),
):
    """Retorna estadísticas de uso para el plan actual (alias para el front)."""
    sub = await service.get_user_subscription(str(current_user.id), db)
    if not sub:
        sub = await service.create_free_subscription(str(current_user.id), db)

    plan_code = None
    if sub.plan_id:
        try:
            import uuid

            plan_id_uuid = uuid.UUID(sub.plan_id)
            plan = db.query(Plan).filter(Plan.id == plan_id_uuid).first()
            plan_code = plan.code if plan else None
        except Exception:
            plan_code = None

    status_value = getattr(sub.status, "value", sub.status)

    return {
        "current_period": {
            "analysis_used": sub.analysis_used,
            "analysis_limit": sub.analysis_limit,
            "analysis_remaining": sub.analysis_remaining,
        },
        "subscription_status": {
            "plan": plan_code,
            "status": status_value,
        },
    }

@router.post("/increment-analysis")
async def increment_analysis(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    service: SubscriptionService = Depends(get_subscription_service)
):
    """Suma 1 al contador de análisis usados del usuario."""
    success = await service.increment_analysis_usage(str(current_user.id), db)
    if not success:
        raise HTTPException(status_code=400, detail="No se pudo incrementar el uso de análisis")
    return {"status": "success", "message": "Análisis incrementado correctamente"}

# ============================================================
# 3. ENDPOINTS DE PAGOS (STRIPE)
# ============================================================

@router.post("/create-checkout-session")
async def create_checkout_session(
    request: PaymentIntentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    service: SubscriptionService = Depends(get_subscription_service)
):
    """Crea una sesión de Checkout de Stripe para el plan seleccionado."""
    try:
        return await service.create_checkout_session(str(current_user.id), request, db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creando checkout session: {e}")
        raise HTTPException(status_code=500, detail="Error interno al procesar el pago")

@router.post("/create-payment-intent", response_model=PaymentIntentResponse)
async def create_payment_intent(
    request: PaymentIntentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    service: SubscriptionService = Depends(get_subscription_service)
):
    """Crea un Payment Intent de Stripe (si usas elementos personalizados de Stripe)."""
    try:
        return await service.create_payment_intent(str(current_user.id), request, db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/cancel")
async def cancel_subscription(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    service: SubscriptionService = Depends(get_subscription_service)
):
    """Cancela la suscripción actual y lo devuelve al plan Free."""
    success = await service.cancel_subscription(str(current_user.id), db)
    if not success:
        raise HTTPException(status_code=400, detail="No tienes una suscripción activa para cancelar")
    return {"status": "success", "message": "Suscripción cancelada exitosamente"}

# ============================================================
# 4. WEBHOOK (ESCUCHA A STRIPE)
# ============================================================

@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    db: Session = Depends(get_db),
    service: SubscriptionService = Depends(get_subscription_service)
):
    """Recibe eventos asíncronos directamente desde Stripe (pagos exitosos, cancelaciones, etc)."""
    try:
        payload = await request.json()
        success = await service.handle_webhook_event(payload, db)
        if not success:
            logger.warning("Evento de webhook no manejado o ignorado")
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error procesando webhook: {e}")
        raise HTTPException(status_code=400, detail="Error procesando webhook")