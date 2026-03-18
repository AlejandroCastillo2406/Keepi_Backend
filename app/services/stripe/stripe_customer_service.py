"""
Creación de clientes en Stripe.
Responsabilidad única: llamar a Stripe API para crear/obtener customer.
"""
import logging

import stripe

from app.models.user import User
from app.services.stripe.stripe_config import ensure_stripe_key

logger = logging.getLogger(__name__)


class StripeCustomerService:
    """Crea clientes en Stripe a partir de un User."""

    def create_customer(self, user: User) -> str:
        """
        Crea un cliente en Stripe para el usuario.
        Returns: stripe_customer_id
        Raises: ValueError si no hay API key; stripe.Error en fallos de API.
        """
        ensure_stripe_key()
        payload = {
            "email": user.email,
            "metadata": {"user_id": str(user.id)},
        }
        if user.name:
            payload["name"] = user.name
        customer = stripe.Customer.create(**payload)
        if not customer or not getattr(customer, "id", None):
            raise ValueError("Stripe devolvió un cliente sin id")
        logger.info("Cliente Stripe creado: %s para user %s", customer.id, user.id)
        return customer.id
