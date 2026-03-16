import uuid
from sqlalchemy import Column, String, DateTime, Boolean, Integer, Float, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from enum import Enum

class SubscriptionStatus(str, Enum):
    """Estados de suscripción"""
    ACTIVE = "active"
    INACTIVE = "inactive" 
    CANCELED = "canceled"
    PAST_DUE = "past_due"
    TRIALING = "trialing"

class SubscriptionPlan(str, Enum):
    """Planes de suscripción"""
    FREE = "free"
    PREMIUM = "premium"
    ENTERPRISE = "enterprise"

# Modelo SQLAlchemy para suscripciones
class Subscription(Base):
    __tablename__ = "subscriptions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True, unique=True)
    
    # Información de Stripe
    stripe_customer_id = Column(String(255), nullable=True, index=True)
    stripe_subscription_id = Column(String(255), nullable=True, index=True)
    stripe_price_id = Column(String(255), nullable=True)
    
    # Detalles de la suscripción
    plan = Column(String(50), nullable=False, default=SubscriptionPlan.FREE)
    status = Column(String(50), nullable=False, default=SubscriptionStatus.INACTIVE)
    trial_end = Column(DateTime(timezone=True), nullable=True)
    current_period_start = Column(DateTime(timezone=True), nullable=True)
    current_period_end = Column(DateTime(timezone=True), nullable=True)
    
    # Límites y uso
    analysis_limit = Column(Integer, nullable=False, default=2)  # 2 análisis gratuitos
    analysis_used = Column(Integer, nullable=False, default=0)
    
    # Metadatos
    extra_metadata = Column(Text, nullable=True)  # JSON como string para metadatos adicionales
    
    # Control de fechas
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    canceled_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relaciones
    user = relationship("User", back_populates="subscription")
    
    def __repr__(self):
        return f"<Subscription(id={self.id}, user_id={self.user_id}, plan={self.plan}, status={self.status})>"
    
    @property
    def has_analysis_remaining(self) -> bool:
        """Verificar si el usuario tiene análisis restantes"""
        if self.plan == SubscriptionPlan.FREE:
            return self.analysis_used < self.analysis_limit
        elif self.plan == SubscriptionPlan.PREMIUM:
            return self.status == SubscriptionStatus.ACTIVE
        return False
    
    @property
    def analysis_remaining(self) -> int:
        """Obtener número de análisis restantes"""
        if self.plan == SubscriptionPlan.FREE:
            return max(0, self.analysis_limit - self.analysis_used)
        elif self.plan == SubscriptionPlan.PREMIUM and self.status == SubscriptionStatus.ACTIVE:
            return 999999  # Ilimitado para plan premium
        return 0

# Modelos Pydantic para la API
class SubscriptionBase(BaseModel):
    """Modelo base para suscripción"""
    plan: SubscriptionPlan = SubscriptionPlan.FREE
    analysis_limit: int = 2

class SubscriptionCreate(SubscriptionBase):
    """Modelo para crear suscripción"""
    user_id: str
    stripe_customer_id: Optional[str] = None
    trial_end: Optional[datetime] = None

class SubscriptionUpdate(BaseModel):
    """Modelo para actualizar suscripción"""
    plan: Optional[SubscriptionPlan] = None
    status: Optional[SubscriptionStatus] = None
    stripe_subscription_id: Optional[str] = None
    stripe_price_id: Optional[str] = None
    trial_end: Optional[datetime] = None
    current_period_start: Optional[datetime] = None
    current_period_end: Optional[datetime] = None
    analysis_limit: Optional[int] = None
    analysis_used: Optional[int] = None
    extra_metadata: Optional[str] = None

class SubscriptionResponse(SubscriptionBase):
    """Modelo de respuesta para suscripción"""
    id: str
    user_id: str
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    stripe_price_id: Optional[str] = None
    status: SubscriptionStatus
    trial_end: Optional[datetime] = None
    current_period_start: Optional[datetime] = None
    current_period_end: Optional[datetime] = None
    analysis_used: int
    has_analysis_remaining: bool
    analysis_remaining: int
    extra_metadata: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    canceled_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True
    
    @classmethod
    def from_orm(cls, obj):
        """Convertir desde ORM asegurando que los UUIDs sean strings"""
        data = {
            "id": str(obj.id),
            "user_id": str(obj.user_id),
            "stripe_customer_id": obj.stripe_customer_id,
            "stripe_subscription_id": obj.stripe_subscription_id,
            "stripe_price_id": obj.stripe_price_id,
            "plan": obj.plan,
            "status": obj.status,
            "trial_end": obj.trial_end,
            "current_period_start": obj.current_period_start,
            "current_period_end": obj.current_period_end,
            "analysis_limit": obj.analysis_limit,
            "analysis_used": obj.analysis_used,
            "has_analysis_remaining": obj.has_analysis_remaining,
            "analysis_remaining": obj.analysis_remaining,
            "extra_metadata": obj.extra_metadata,
            "created_at": obj.created_at,
            "updated_at": obj.updated_at,
            "canceled_at": obj.canceled_at
        }
        return cls(**data)

class PaymentIntentRequest(BaseModel):
    """Modelo para crear Payment Intent de Stripe"""
    plan: SubscriptionPlan
    payment_method_id: Optional[str] = None

class PaymentIntentResponse(BaseModel):
    """Respuesta del Payment Intent"""
    client_secret: str
    status: str
    subscription_id: Optional[str] = None

class WebhookEvent(BaseModel):
    """Modelo para eventos de webhook de Stripe"""
    id: str
    type: str
    data: dict
    created: int
