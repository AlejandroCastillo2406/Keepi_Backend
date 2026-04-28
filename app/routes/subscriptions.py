import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_no_temp_password_user
from app.models.user import User
from app.models.subscription import (
    PaymentIntentRequest,
    PaymentIntentResponse,
    SubscriptionResponse,
)
from app.models.plans import PlanResponse
from app.factories.subscription_factory import get_subscription_service
from app.services.subscription.subscription_service import SubscriptionService

router = APIRouter(tags=["Subscriptions"])
logger = logging.getLogger(__name__)


@router.get("/plans", response_model=List[PlanResponse])
async def get_available_plans(
    db: Session = Depends(get_db),
    service: SubscriptionService = Depends(get_subscription_service),
):
    return await service.list_public_plans(db)


@router.get("/me", response_model=SubscriptionResponse)
async def get_my_subscription(
    current_user: User = Depends(require_no_temp_password_user),
    db: Session = Depends(get_db),
    service: SubscriptionService = Depends(get_subscription_service),
):
    sub = await service.get_user_subscription(str(current_user.id), db)
    if not sub:

        sub = await service.create_free_subscription(str(current_user.id), db)
    return sub


@router.get("/check-analysis-limit")
async def check_analysis_limit(
    current_user: User = Depends(require_no_temp_password_user),
    db: Session = Depends(get_db),
    service: SubscriptionService = Depends(get_subscription_service),
):
    return await service.check_analysis_limit(str(current_user.id), db)


@router.get("/usage-stats")
async def usage_stats(
    current_user: User = Depends(require_no_temp_password_user),
    db: Session = Depends(get_db),
    service: SubscriptionService = Depends(get_subscription_service),
):
    return await service.build_usage_stats(db, str(current_user.id))


@router.post("/increment-analysis")
async def increment_analysis(
    current_user: User = Depends(require_no_temp_password_user),
    db: Session = Depends(get_db),
    service: SubscriptionService = Depends(get_subscription_service),
):
    success = await service.increment_analysis_usage(str(current_user.id), db)
    if not success:
        raise HTTPException(
            status_code=400, detail="No se pudo incrementar el uso de análisis"
        )
    return {"status": "success", "message": "Análisis incrementado correctamente"}


@router.post("/create-checkout-session")
async def create_checkout_session(
    request: PaymentIntentRequest,
    current_user: User = Depends(require_no_temp_password_user),
    db: Session = Depends(get_db),
    service: SubscriptionService = Depends(get_subscription_service),
):
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
    current_user: User = Depends(require_no_temp_password_user),
    db: Session = Depends(get_db),
    service: SubscriptionService = Depends(get_subscription_service),
):
    try:
        return await service.create_payment_intent(str(current_user.id), request, db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/cancel")
async def cancel_subscription(
    current_user: User = Depends(require_no_temp_password_user),
    db: Session = Depends(get_db),
    service: SubscriptionService = Depends(get_subscription_service),
):
    success = await service.cancel_subscription(str(current_user.id), db)
    if not success:
        raise HTTPException(
            status_code=400, detail="No tienes una suscripción activa para cancelar"
        )
    return {"status": "success", "message": "Suscripción cancelada exitosamente"}


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    db: Session = Depends(get_db),
    service: SubscriptionService = Depends(get_subscription_service),
):
    try:
        payload = await request.json()
        success = await service.handle_webhook_event(payload, db)
        if not success:
            logger.warning("Evento de webhook no manejado o ignorado")
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error procesando webhook: {e}")
        raise HTTPException(status_code=400, detail="Error procesando webhook")
