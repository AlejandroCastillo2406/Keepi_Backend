import logging
from datetime import datetime
from typing import Any, Dict, Optional

import stripe

from app.services.stripe.stripe_config import ensure_stripe_key

logger = logging.getLogger(__name__)


class StripeSubscriptionService:

    def create_subscription(
        self,
        customer_id: str,
        price_id: str,
        user_id: str,
        plan_value: str,
    ) -> Dict[str, Any]:
        ensure_stripe_key()
        sub = stripe.Subscription.create(
            customer=customer_id,
            items=[{"price": price_id}],
            payment_behavior="default_incomplete",
            payment_settings={"save_default_payment_method": "on_subscription"},
            expand=["latest_invoice.payment_intent"],
            metadata={"user_id": str(user_id), "plan": plan_value},
        )
        logger.info("Suscripción Stripe creada: %s para user %s", sub.id, user_id)
        pi = (
            getattr(sub.latest_invoice, "payment_intent", None)
            if sub.latest_invoice
            else None
        )
        return {
            "stripe_subscription": sub,
            "stripe_subscription_id": sub.id,
            "current_period_start": datetime.fromtimestamp(sub.current_period_start),
            "current_period_end": datetime.fromtimestamp(sub.current_period_end),
            "payment_intent_id": getattr(pi, "id", None) if pi else None,
            "client_secret": getattr(pi, "client_secret", None) if pi else None,
            "status": getattr(pi, "status", None) if pi else None,
        }

    def cancel_subscription(self, stripe_subscription_id: str) -> None:
        ensure_stripe_key()
        stripe.Subscription.delete(stripe_subscription_id)
        logger.info("Suscripción Stripe cancelada: %s", stripe_subscription_id)

    def retrieve_subscription(self, stripe_subscription_id: str) -> Optional[Any]:
        try:
            ensure_stripe_key()
            return stripe.Subscription.retrieve(stripe_subscription_id)
        except stripe.error.StripeError:
            return None
