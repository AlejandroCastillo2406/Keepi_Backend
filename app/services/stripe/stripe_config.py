"""
Configuración de Stripe: API key y URLs de pago.
Una sola responsabilidad: exponer configuración validada para el resto de servicios Stripe.
"""
import logging
from typing import Tuple

import stripe

from app.config.settings import settings

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
    if plan == "premium":
        if not settings.stripe_premium_price_id:
            raise ValueError("STRIPE_PREMIUM_PRICE_ID no configurado en variables de entorno")
        return settings.stripe_premium_price_id
    raise ValueError(f"Plan no válido o STRIPE_PREMIUM_PRICE_ID no configurado: {plan}")


def get_payment_urls() -> Tuple[str, str]:
    """Devuelve (success_url, cancel_url) para checkout. Usa STRIPE_*_URL o deriva de PUBLIC_BASE_URL."""
    success = (settings.stripe_payment_success_url or "").strip()
    cancel = (settings.stripe_payment_cancel_url or "").strip()
    base = (settings.public_base_url or "").strip().rstrip("/")
    if not success and base:
        success = f"{base}/payment/success?session_id={{CHECKOUT_SESSION_ID}}"
    if not cancel and base:
        cancel = f"{base}/payment/cancel"
    if not success or not cancel:
        raise ValueError(
            "Configura STRIPE_PAYMENT_SUCCESS_URL y STRIPE_PAYMENT_CANCEL_URL, o PUBLIC_BASE_URL en el entorno"
        )
    return (success, cancel)


# Configurar API key al importar el módulo (para uso directo de stripe en rutas, p. ej. Invoice.list)
if getattr(settings, "stripe_secret_key", None):
    stripe.api_key = settings.stripe_secret_key
