"""
Creación de Checkout Sessions de Stripe (flujo de pago por redirección).
Responsabilidad única: crear la sesión de checkout y devolver URL y metadatos.
"""
import logging
from typing import Any, Dict

import stripe

from app.services.stripe.stripe_config import ensure_stripe_key, get_payment_urls

logger = logging.getLogger(__name__)


class StripeCheckoutService:
    """Crea sesiones de checkout de Stripe para suscripciones."""

    def create_checkout_session(
        self,
        customer_id: str,
        price_id: str,
        user_id: str,
        plan_value: str,
    ) -> Dict[str, Any]:
        """
        Crea una Checkout Session en modo subscription.
        Returns: dict con checkout_session_id, checkout_url, success_url, cancel_url.
        """
        ensure_stripe_key()
        success_url, cancel_url = get_payment_urls()
        session = stripe.checkout.Session.create(
            customer=customer_id,
            payment_method_types=["card"],
            line_items=[{"price": price_id, "quantity": 1}],
            mode="subscription",
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={"user_id": str(user_id), "plan": plan_value},
        )
        logger.info("Checkout Session creada: %s", session.id)
        return {
            "checkout_session_id": session.id,
            "checkout_url": session.url,
            "success_url": success_url,
            "cancel_url": cancel_url,
            "stripe_customer_id": customer_id,
        }
