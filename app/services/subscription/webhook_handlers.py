import logging
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.subscription import SubscriptionStatus
from app.repositories.subscription_repository import SubscriptionRepository
from app.repositories.user_repository import UserRepository
from app.services.notificaciones.payment_email_service import send_payment_email_ses
from app.services.stripe.checkout_session_receipt import (
    build_receipt_from_checkout_session,
)
from app.services.stripe.stripe_subscription_service import StripeSubscriptionService

logger = logging.getLogger(__name__)

STRIPE_STATUS_TO_OURS = {
    "active": SubscriptionStatus.ACTIVE,
    "canceled": SubscriptionStatus.CANCELED,
    "past_due": SubscriptionStatus.PAST_DUE,
    "trialing": SubscriptionStatus.TRIALING,
    "incomplete": SubscriptionStatus.INACTIVE,
    "incomplete_expired": SubscriptionStatus.INACTIVE,
}


def _normalize_event(event_data: Any) -> Tuple[Optional[str], Dict[str, Any]]:
    event_type = (
        event_data.get("type")
        if isinstance(event_data, dict)
        else getattr(event_data, "type", None)
    )
    data = (
        event_data.get("data", {})
        if isinstance(event_data, dict)
        else getattr(event_data, "data", {})
    )
    data_object = (
        data.get("object", {})
        if isinstance(data, dict)
        else getattr(data, "object", {})
    )
    if data_object is not None and not isinstance(data_object, dict):
        try:
            import stripe

            data_object = (
                stripe.util.convert_to_dict(data_object)
                if hasattr(stripe, "util")
                else dict(data_object)
            )
        except Exception:
            data_object = {}
    data_object = data_object or {}
    return event_type, data_object


def handle_webhook_event(event_data: Any, db: Session) -> bool:
    event_type, data_object = _normalize_event(event_data)
    repo = SubscriptionRepository(db)
    stripe_svc = StripeSubscriptionService()
    try:
        if not event_type:
            logger.warning("Webhook sin tipo de evento")
            return True
        if event_type == "customer.subscription.created":
            _handle_subscription_created(data_object, repo, stripe_svc)
        elif event_type == "customer.subscription.updated":
            _handle_subscription_updated(data_object, repo)
        elif event_type == "customer.subscription.deleted":
            _handle_subscription_deleted(data_object, repo)
        elif event_type == "invoice.payment_succeeded":
            _handle_payment_succeeded(data_object, repo)
        elif event_type == "invoice.payment_failed":
            _handle_payment_failed(data_object, repo)
        elif event_type == "checkout.session.completed":
            _handle_checkout_session_completed(data_object, repo, stripe_svc, db)
        else:
            logger.info("Evento webhook no manejado: %s", event_type)
        return True
    except Exception as e:
        logger.exception("Error manejando webhook %s: %s", event_type, e)
        db.rollback()
        return False


def _handle_checkout_session_completed(
    session_data: Dict[str, Any],
    repo: SubscriptionRepository,
    stripe_svc: StripeSubscriptionService,
    db: Session,
) -> None:
    session_id = session_data.get("id")
    customer_id = session_data.get("customer")
    subscription_id = session_data.get("subscription")
    mode = session_data.get("mode")
    payment_status = session_data.get("payment_status")

    if not customer_id:
        logger.warning("Checkout session sin customer_id: %s", session_id)
        return
    subscription = repo.get_by_stripe_customer_id(customer_id)
    if not subscription:
        logger.warning("No se encontró suscripción para customer: %s", customer_id)
        return
    if not subscription_id:
        logger.warning("Checkout session sin subscription_id: %s", session_id)
        return

    send_confirmation = mode == "subscription" and payment_status in (
        "paid",
        "no_payment_required",
    )
    if mode == "subscription" and payment_status not in ("paid", "no_payment_required"):
        logger.info(
            "Checkout session %s sin pago confirmado aún (payment_status=%s); no se envía correo",
            session_id,
            payment_status,
        )

    stripe_sub = stripe_svc.retrieve_subscription(subscription_id)
    period_start = (
        datetime.fromtimestamp(stripe_sub.current_period_start) if stripe_sub else None
    )
    period_end = (
        datetime.fromtimestamp(stripe_sub.current_period_end) if stripe_sub else None
    )
    repo.set_premium_after_checkout(
        subscription, subscription_id, period_start, period_end
    )
    logger.info("Suscripción actualizada a Premium: %s", subscription.id)

    if not send_confirmation:
        return

    user = UserRepository(db).get_by_id_plain(subscription.user_id)
    if not user or not user.email:
        logger.warning(
            "No se envía correo de confirmación de pago: usuario %s sin email",
            subscription.user_id,
        )
        return

    receipt = build_receipt_from_checkout_session(
        str(session_id),
        dict(session_data),
    )
    result = send_payment_email_ses(
        to_email=user.email,
        kind="success",
        user_name=user.name if getattr(user, "name", None) else None,
        receipt=receipt,
    )
    if result.success:
        logger.info("Correo de confirmación de pago enviado a %s", user.email)
    else:
        logger.warning(
            "Falló envío de correo confirmación de pago a %s: %s",
            user.email,
            result.error,
        )


def _handle_subscription_created(
    data: Dict[str, Any],
    repo: SubscriptionRepository,
    stripe_svc: StripeSubscriptionService,
) -> None:
    stripe_sub_id = data.get("id")
    customer_id = data.get("customer")
    subscription = repo.get_by_stripe_customer_id(customer_id) if customer_id else None
    if not subscription and stripe_sub_id:
        subscription = repo.get_by_stripe_subscription_id(stripe_sub_id)
    if not subscription:
        logger.warning(
            "Suscripción creada sin subscription local (customer_id=%s)", customer_id
        )
        return
    period_start = (
        datetime.fromtimestamp(data["current_period_start"])
        if data.get("current_period_start")
        else None
    )
    period_end = (
        datetime.fromtimestamp(data["current_period_end"])
        if data.get("current_period_end")
        else None
    )
    repo.set_premium_after_checkout(
        subscription, stripe_sub_id, period_start, period_end
    )
    logger.info("Suscripción creada/activada: %s", stripe_sub_id)


def _handle_subscription_updated(
    data: Dict[str, Any], repo: SubscriptionRepository
) -> None:
    stripe_sub_id = data.get("id")
    status = data.get("status")
    subscription = repo.get_by_stripe_subscription_id(stripe_sub_id)
    if not subscription:
        return
    if status == "canceled":
        repo.set_canceled_to_free(subscription)
    else:
        our_status = STRIPE_STATUS_TO_OURS.get(status, SubscriptionStatus.INACTIVE)
        period_start = (
            datetime.fromtimestamp(data["current_period_start"])
            if data.get("current_period_start")
            else None
        )
        period_end = (
            datetime.fromtimestamp(data["current_period_end"])
            if data.get("current_period_end")
            else None
        )
        repo.set_status(subscription, our_status, period_start, period_end)
    logger.info("Suscripción actualizada: %s - %s", stripe_sub_id, status)


def _handle_subscription_deleted(
    data: Dict[str, Any], repo: SubscriptionRepository
) -> None:
    stripe_sub_id = data.get("id")
    subscription = repo.get_by_stripe_subscription_id(stripe_sub_id)
    if subscription:
        repo.set_canceled_to_free(subscription)
        logger.info("Suscripción cancelada: %s", stripe_sub_id)


def _handle_payment_succeeded(
    data: Dict[str, Any], repo: SubscriptionRepository
) -> None:
    subscription_id = data.get("subscription")
    if not subscription_id:
        return
    subscription = repo.get_by_stripe_subscription_id(subscription_id)
    if subscription:
        repo.set_status(subscription, SubscriptionStatus.ACTIVE)
        logger.info("Pago exitoso para suscripción: %s", subscription_id)


def _handle_payment_failed(data: Dict[str, Any], repo: SubscriptionRepository) -> None:
    subscription_id = data.get("subscription")
    if not subscription_id:
        return
    subscription = repo.get_by_stripe_subscription_id(subscription_id)
    if subscription:
        repo.set_status(subscription, SubscriptionStatus.PAST_DUE)
        logger.warning("Pago fallido para suscripción: %s", subscription_id)
