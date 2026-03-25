import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class SubscriptionStatus(str, Enum):
    """Estados de suscripción"""
    ACTIVE = "active"
    INACTIVE = "inactive" 
    CANCELED = "canceled"
    PAST_DUE = "past_due"
    TRIALING = "trialing"

# NOTA: Hemos eliminado SubscriptionPlan (Enum) porque ahora 
# la información de los planes es dinámica y viene de la base de datos.

# Modelo SQLAlchemy para suscripciones
class Subscription(Base):
    __tablename__ = "subscriptions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True, unique=True)
    
    # NUEVO: Llave foránea que enlaza con la tabla de planes
    plan_id = Column(UUID(as_uuid=True), ForeignKey("plans.id"), nullable=True, index=True)
    
    # Información de Stripe
    stripe_customer_id = Column(String(255), nullable=True, index=True)
    stripe_subscription_id = Column(String(255), nullable=True, index=True)
    stripe_price_id = Column(String(255), nullable=True)
    
    # Detalles de la suscripción
    status = Column(String(50), nullable=False, default=SubscriptionStatus.INACTIVE)
    trial_end = Column(DateTime(timezone=True), nullable=True)
    current_period_start = Column(DateTime(timezone=True), nullable=True)
    current_period_end = Column(DateTime(timezone=True), nullable=True)
    
    # Límites y uso (Se copian del Plan al usuario para mantener un historial seguro)
    # Convención: -1 significa análisis ilimitados
    analysis_limit = Column(Integer, nullable=False, default=2)  
    analysis_used = Column(Integer, nullable=False, default=0)
    
    # Metadatos
    extra_metadata = Column(Text, nullable=True)  # JSON como string para metadatos adicionales
    
    # Control de fechas
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    canceled_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relaciones
    user = relationship("User", back_populates="subscription")
    plan = relationship("Plan") # <--- Relación con el modelo creado en el Paso 1
    
    def __repr__(self):
        return f"<Subscription(id={self.id}, user_id={self.user_id}, plan_id={self.plan_id}, status={self.status})>"
    
    @property
    def has_analysis_remaining(self) -> bool:
        """Verificar dinámicamente si el usuario tiene análisis restantes"""
        if self.analysis_limit == -1: # -1 = Ilimitado
            return self.status == SubscriptionStatus.ACTIVE
        return self.analysis_used < self.analysis_limit
    
    @property
    def analysis_remaining(self) -> int:
        """Obtener número de análisis restantes dinámicamente"""
        if self.analysis_limit == -1: # -1 = Ilimitado
            return 999999 if self.status == SubscriptionStatus.ACTIVE else 0
        return max(0, self.analysis_limit - self.analysis_used)


# Modelos Pydantic para la API
class SubscriptionBase(BaseModel):
    """Modelo base para suscripción"""
    plan_id: Optional[str] = None
    analysis_limit: int = 2

class SubscriptionCreate(SubscriptionBase):
    """Modelo para crear suscripción"""
    user_id: str
    stripe_customer_id: Optional[str] = None
    trial_end: Optional[datetime] = None

class SubscriptionUpdate(BaseModel):
    """Modelo para actualizar suscripción"""
    plan_id: Optional[str] = None
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
            "plan_id": str(obj.plan_id) if obj.plan_id else None,
            "stripe_customer_id": obj.stripe_customer_id,
            "stripe_subscription_id": obj.stripe_subscription_id,
            "stripe_price_id": obj.stripe_price_id,
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
    # En lugar de usar un Enum cerrado, recibimos el "código" del plan (ej. "premium")
    plan_code: str 
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