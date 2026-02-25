"""
Configuración de Stripe: API key y URLs de pago.
Una sola responsabilidad: exponer configuración validada para el resto de servicios Stripe.
"""
import logging
from typing import Tuple

from app.config.settings import settings
import stripe

logger = logging.getLogger(__name__)


def ensure_stripe_key() -> None:
    """Asegura que stripe.api_key esté configurada. Lanza ValueError si no hay key."""
    if stripe.api_key:
        return
    stripe.api_key = settings.stripe_secret_key
    if not stripe.api_key:
        raise ValueError("STRIPE_SECRET_KEY no configurada en variables de entorno")


def get_price_id_for_plan(plan: str) -> str:
    """Devuelve el Stripe Price ID para un plan. Lanza ValueError si el plan no es válido."""
    price_id = settings.stripe_premium_price_id or "price_premium_test"
    if plan == "premium":
        return price_id
    raise ValueError(f"Plan no válido o STRIPE_PREMIUM_PRICE_ID no configurado: {plan}")


def get_payment_urls() -> Tuple[str, str]:
    """Devuelve (success_url, cancel_url) para checkout."""
    return (
        settings.stripe_payment_success_url,
        settings.stripe_payment_cancel_url,
    )


# Configurar API key al importar el módulo (para uso directo de stripe en rutas, p. ej. Invoice.list)
if getattr(settings, "stripe_secret_key", None):
    stripe.api_key = settings.stripe_secret_key
