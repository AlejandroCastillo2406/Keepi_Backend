import logging
import uuid
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.models.subscription import PaymentIntentRequest, PaymentIntentResponse, Subscription, SubscriptionResponse, SubscriptionStatus
from app.models.plans import Plan
from app.models.user import User
from app.repositories.subscription_repository import SubscriptionRepository
from app.services.stripe.stripe_checkout_service import StripeCheckoutService
from app.services.stripe.stripe_config import get_price_id_for_plan
from app.services.stripe.stripe_customer_service import StripeCustomerService
from app.services.stripe.stripe_subscription_service import StripeSubscriptionService
from app.services.subscription.webhook_handlers import handle_webhook_event

logger = logging.getLogger(__name__)


def _effective_analysis_limit(db: Session, subscription: Subscription) -> int:
    """
    El límite mostrado y aplicado debe seguir al plan actual en `plans`,
    no solo a la copia en `subscriptions` (puede quedar obsoleta si editas el plan en BD).
    """
    if subscription.plan_id:
        plan = db.query(Plan).filter(Plan.id == subscription.plan_id).first()
        if plan is not None:
            return int(plan.analysis_limit)
    return int(subscription.analysis_limit)


def _analysis_remaining_with_limit(subscription: Subscription, limit: int) -> int:
    if limit == -1:
        return 999999 if subscription.status == SubscriptionStatus.ACTIVE else 0
    return max(0, limit - int(subscription.analysis_used))


def _has_analysis_remaining_with_limit(subscription: Subscription, limit: int) -> bool:
    if limit == -1:
        return subscription.status == SubscriptionStatus.ACTIVE
    return int(subscription.analysis_used) < limit


class SubscriptionService:
    def __init__(
        self, 
        stripe_customer: Optional[StripeCustomerService] = None, 
        stripe_checkout: Optional[StripeCheckoutService] = None, 
        stripe_subscription: Optional[StripeSubscriptionService] = None, 
    ) -> None:
        self._stripe_customer = stripe_customer or StripeCustomerService()
        self._stripe_checkout = stripe_checkout or StripeCheckoutService()
        self._stripe_subscription = stripe_subscription or StripeSubscriptionService()

    def subscription_response_with_plan_limits(
        self, db: Session, sub: Subscription
    ) -> SubscriptionResponse:
        base = SubscriptionResponse.from_orm(sub)
        limit = _effective_analysis_limit(db, sub)
        remaining = _analysis_remaining_with_limit(sub, limit)
        has_rem = _has_analysis_remaining_with_limit(sub, limit)
        if (
            limit == base.analysis_limit
            and remaining == base.analysis_remaining
            and has_rem == base.has_analysis_remaining
        ):
            return base
        return base.model_copy(
            update={
                "analysis_limit": limit,
                "analysis_remaining": remaining,
                "has_analysis_remaining": has_rem,
            }
        )

    async def get_user_subscription(self, user_id: str, db: Session) -> Optional[SubscriptionResponse]:
        repo = SubscriptionRepository(db)
        sub = repo.get_by_user_id(user_id)
        return self.subscription_response_with_plan_limits(db, sub) if sub else None

    async def get_or_create_subscription(self, user_id: str, db: Session) -> Subscription:
        repo = SubscriptionRepository(db)
        return repo.get_or_create_free(user_id)

    async def create_free_subscription(self, user_id: str, db: Session) -> SubscriptionResponse:
        repo = SubscriptionRepository(db)
        sub = repo.get_or_create_free(user_id)
        return self.subscription_response_with_plan_limits(db, sub)

    async def create_checkout_session(self, user_id: str, request: PaymentIntentRequest, db: Session) -> Dict[str, Any]:
        repo = SubscriptionRepository(db)
        try:
            user_uuid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id
        except (ValueError, TypeError):
            raise ValueError("user_id inválido") from None

        user = db.query(User).filter(User.id == user_uuid).first()
        if not user:
            raise ValueError("Usuario no encontrado")

        subscription = await self.get_or_create_subscription(user_id, db)
        if not subscription.stripe_customer_id:
            customer_id = self._stripe_customer.create_customer(user)
            repo.set_stripe_customer_id(subscription, customer_id)
            subscription = repo.get_by_user_id(user_id)

        if request.plan_code != "premium":
            raise ValueError("Solo se soporta el plan premium para crear checkout session")
        price_id = get_price_id_for_plan("premium")

        return self._stripe_checkout.create_checkout_session(
            customer_id=subscription.stripe_customer_id, 
            price_id=price_id, 
            user_id=str(user_id), 
            plan_value=request.plan_code, 
        )

    async def create_payment_intent(self, user_id: str, request: PaymentIntentRequest, db: Session) -> PaymentIntentResponse:
        repo = SubscriptionRepository(db)
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError("Usuario no encontrado")

        subscription = repo.get_by_user_id(user_id)
        if not subscription:
            subscription = repo.create_free(user_id)

        if not subscription.stripe_customer_id:
            customer_id = self._stripe_customer.create_customer(user)
            repo.set_stripe_customer_id(subscription, customer_id)
            subscription = repo.get_by_user_id(user_id)

        if request.plan_code != "premium":
            raise ValueError("Solo se soporta el plan premium para crear payment intent")
        price_id = get_price_id_for_plan("premium")

        result = self._stripe_subscription.create_subscription(
            customer_id=subscription.stripe_customer_id, 
            price_id=price_id, 
            user_id=str(user_id), 
            plan_value=request.plan_code, 
        )

        repo.set_payment_intent_created(
            subscription, 
            stripe_subscription_id=result["stripe_subscription_id"], 
            stripe_price_id=price_id, 
            plan_code=request.plan_code, 
            current_period_start=result["current_period_start"], 
            current_period_end=result["current_period_end"], 
        )

        return PaymentIntentResponse(
            client_secret=result.get("client_secret") or "", 
            status=result.get("status") or "requires_payment_method", 
            subscription_id=result["stripe_subscription_id"], 
        )

    async def handle_webhook_event(self, event_data: Dict[str, Any], db: Session) -> bool:
        return handle_webhook_event(event_data, db)

    async def cancel_subscription(self, user_id: str, db: Session) -> bool:
        repo = SubscriptionRepository(db)
        subscription = repo.get_by_user_id(user_id)
        if not subscription or not subscription.stripe_subscription_id:
            logger.warning("No hay suscripción activa para usuario %s", user_id)
            return False
            
        self._stripe_subscription.cancel_subscription(subscription.stripe_subscription_id)
        repo.set_canceled_to_free(subscription)
        logger.info("Suscripción cancelada para usuario %s", user_id)
        return True

    async def check_analysis_limit(self, user_id: str, db: Session) -> Dict[str, Any]:
        repo = SubscriptionRepository(db)
        subscription = repo.get_or_create_free(user_id)
        limit = _effective_analysis_limit(db, subscription)
        can_analyze = _has_analysis_remaining_with_limit(subscription, limit)
        remaining = _analysis_remaining_with_limit(subscription, limit)

        current_plan_code = None
        if subscription.plan_id:
            plan = db.query(Plan).filter(Plan.id == subscription.plan_id).first()
            if plan:
                current_plan_code = plan.code

        return {
            "can_analyze": can_analyze,
            "analysis_remaining": remaining,
            "analysis_used": subscription.analysis_used,
            "plan": current_plan_code or "none",
            "status": subscription.status,
            "needs_subscription": not can_analyze and current_plan_code != "premium",
        }

    async def increment_analysis_usage(self, user_id: str, db: Session) -> bool:
        repo = SubscriptionRepository(db)
        subscription = repo.get_by_user_id(user_id)
        if not subscription:
            logger.warning("No hay suscripción para usuario %s", user_id)
            return False
        return repo.increment_analysis_used(subscription)