import uuid
from datetime import datetime
from typing import Optional, Union

from sqlalchemy.orm import Session

from app.models.subscription import Subscription, SubscriptionStatus
from app.models.plans import Plan


class SubscriptionRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_plan_by_code(self, plan_code: str) -> Plan:
        plan = self._db.query(Plan).filter(Plan.code == plan_code).first()
        if not plan:
            raise ValueError(f"Plan no encontrado en base de datos: {plan_code}")
        return plan

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
        return self._db.query(Subscription).filter(Subscription.stripe_customer_id == stripe_customer_id).first()

    def get_by_stripe_subscription_id(self, stripe_subscription_id: str) -> Optional[Subscription]:
        return self._db.query(Subscription).filter(Subscription.stripe_subscription_id == stripe_subscription_id).first()

    def create_free(self, user_id: Union[str, uuid.UUID]) -> Subscription:
        uid = self._to_uuid(user_id)

        free_plan = self.get_plan_by_code("free")
        sub = Subscription(
            user_id=uid,
            plan_id=free_plan.id,
            status=SubscriptionStatus.ACTIVE,
            analysis_limit=free_plan.analysis_limit,
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
        period_start: Optional[datetime] = None,
        period_end: Optional[datetime] = None,
    ) -> None:
        premium_plan = self.get_plan_by_code("premium")

        subscription.stripe_subscription_id = stripe_subscription_id
        subscription.plan_id = premium_plan.id
        subscription.status = SubscriptionStatus.ACTIVE
        subscription.analysis_limit = premium_plan.analysis_limit
        subscription.analysis_used = 0
        if period_start is not None:
            subscription.current_period_start = period_start
        if period_end is not None:
            subscription.current_period_end = period_end
        self._db.commit()
        self._db.refresh(subscription)

    def set_status(self, subscription: Subscription, status: SubscriptionStatus, current_period_start: Optional[datetime] = None, current_period_end: Optional[datetime] = None) -> None:
        subscription.status = status
        if current_period_start is not None:
            subscription.current_period_start = current_period_start
        if current_period_end is not None:
            subscription.current_period_end = current_period_end
        self._db.commit()
        self._db.refresh(subscription)

    def set_canceled_to_free(self, subscription: Subscription) -> None:
        free_plan = self.get_plan_by_code("free")

        subscription.status = SubscriptionStatus.CANCELED
        subscription.canceled_at = datetime.utcnow()
        subscription.plan_id = free_plan.id
        subscription.analysis_limit = free_plan.analysis_limit
        self._db.commit()
        self._db.refresh(subscription)

    def set_payment_intent_created(self, subscription: Subscription, stripe_subscription_id: str, stripe_price_id: str, plan_code: str, current_period_start: datetime, current_period_end: datetime) -> None:
        target_plan = self.get_plan_by_code(plan_code)

        subscription.stripe_subscription_id = stripe_subscription_id
        subscription.stripe_price_id = stripe_price_id
        subscription.plan_id = target_plan.id
        subscription.status = SubscriptionStatus.INACTIVE
        subscription.current_period_start = current_period_start
        subscription.current_period_end = current_period_end
        subscription.analysis_limit = target_plan.analysis_limit
        self._db.commit()
        self._db.refresh(subscription)

    def increment_analysis_used(self, subscription: Subscription) -> bool:
        subscription.analysis_used += 1
        self._db.commit()
        self._db.refresh(subscription)
        return True