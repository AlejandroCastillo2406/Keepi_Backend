from app.services.subscription.subscription_service import SubscriptionService


def get_subscription_service() -> SubscriptionService:
    return SubscriptionService()
