"""
Repositorio de suscripciones: solo acceso a datos (queries sobre Subscription).
Sin lógica de negocio ni llamadas a Stripe.
"""
import uuid
from datetime import datetime
from typing import Optional, Union

from sqlalchemy.orm import Session

from app.core.constants import ANALYSIS_LIMIT_FREE, ANALYSIS_LIMIT_PREMIUM_UNLIMITED
from app.models.subscription import (
    Subscription,
    SubscriptionPlan,
    SubscriptionStatus,
)


class SubscriptionRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def _to_uuid(self, user_id: Union[str, uuid.UUID]) -> uuid.UUID:
        if isinstance(user_id, uuid.UUID):
            return user_id
        try:
            return uuid.UUID(str(user_id))
        except (ValueError, TypeError):
            raise ValueError("user_id inválido") from None

    def get_by_user_id(self, user_id: Union[str, uuid.UUID]) -> Optional[Subscription]:
        uid = self._to_uuid(user_id)
        return (
            self._db.query(Subscription)
            .filter(Subscription.user_id == uid)
            .first()
        )

    def get_by_stripe_customer_id(self, stripe_customer_id: str) -> Optional[Subscription]:
        return (
            self._db.query(Subscription)
            .filter(Subscription.stripe_customer_id == stripe_customer_id)
            .first()
        )

    def get_by_stripe_subscription_id(self, stripe_subscription_id: str) -> Optional[Subscription]:
        return (
            self._db.query(Subscription)
            .filter(Subscription.stripe_subscription_id == stripe_subscription_id)
            .first()
        )

    def create_free(self, user_id: Union[str, uuid.UUID]) -> Subscription:
        uid = self._to_uuid(user_id)
        sub = Subscription(
            user_id=uid,
            plan=SubscriptionPlan.FREE,
            status=SubscriptionStatus.ACTIVE,
            analysis_limit=ANALYSIS_LIMIT_FREE,
            analysis_used=0,
        )
        self._db.add(sub)
        self._db.commit()
        self._db.refresh(sub)
        return sub

    def get_or_create_free(self, user_id: Union[str, uuid.UUID]) -> Subscription:
        existing = self.get_by_user_id(user_id)
        if existing:
            return existing
        return self.create_free(user_id)

    def set_stripe_customer_id(self, subscription: Subscription, customer_id: str) -> None:
        subscription.stripe_customer_id = customer_id
        self._db.commit()
        self._db.refresh(subscription)

    def set_premium_after_checkout(
        self,
        subscription: Subscription,
        stripe_subscription_id: str,
        current_period_start: Optional[datetime] = None,
        current_period_end: Optional[datetime] = None,
    ) -> None:
        subscription.stripe_subscription_id = stripe_subscription_id
        subscription.plan = SubscriptionPlan.PREMIUM
        subscription.status = SubscriptionStatus.ACTIVE
        subscription.analysis_limit = ANALYSIS_LIMIT_PREMIUM_UNLIMITED
        subscription.analysis_used = 0
        if current_period_start is not None:
            subscription.current_period_start = current_period_start
        if current_period_end is not None:
            subscription.current_period_end = current_period_end
        self._db.commit()
        self._db.refresh(subscription)

    def set_status(
        self,
        subscription: Subscription,
        status: SubscriptionStatus,
        current_period_start: Optional[datetime] = None,
        current_period_end: Optional[datetime] = None,
    ) -> None:
        subscription.status = status
        if current_period_start is not None:
            subscription.current_period_start = current_period_start
        if current_period_end is not None:
            subscription.current_period_end = current_period_end
        self._db.commit()
        self._db.refresh(subscription)

    def set_canceled_to_free(self, subscription: Subscription) -> None:
        subscription.status = SubscriptionStatus.CANCELED
        subscription.canceled_at = datetime.utcnow()
        subscription.plan = SubscriptionPlan.FREE
        subscription.analysis_limit = ANALYSIS_LIMIT_FREE
        self._db.commit()
        self._db.refresh(subscription)

    def set_payment_intent_created(
        self,
        subscription: Subscription,
        stripe_subscription_id: str,
        stripe_price_id: str,
        plan: SubscriptionPlan,
        current_period_start: datetime,
        current_period_end: datetime,
    ) -> None:
        subscription.stripe_subscription_id = stripe_subscription_id
        subscription.stripe_price_id = stripe_price_id
        subscription.plan = plan
        subscription.status = SubscriptionStatus.INACTIVE
        subscription.current_period_start = current_period_start
        subscription.current_period_end = current_period_end
        subscription.analysis_limit = ANALYSIS_LIMIT_PREMIUM_UNLIMITED
        self._db.commit()
        self._db.refresh(subscription)

    def increment_analysis_used(self, subscription: Subscription) -> bool:
        subscription.analysis_used += 1
        self._db.commit()
        self._db.refresh(subscription)
        return True
