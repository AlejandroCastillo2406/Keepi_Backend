import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel
from sqlalchemy import JSON, Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.core.database import Base


class Plan(Base):
    __tablename__ = "plans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    code = Column(String(50), unique=True, index=True, nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    price = Column(Integer, nullable=False, default=0)
    currency = Column(String(10), nullable=False, default="MXN")
    interval = Column(String(50), nullable=False, default="month")
    stripe_price_id = Column(String(255), nullable=True)

    analysis_limit = Column(Integer, nullable=False, default=2)

    features = Column(JSON, nullable=True, default=list)
    is_active = Column(Boolean, default=True, nullable=False)
    recommended = Column(Boolean, default=False, nullable=False)

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self):
        return f"<Plan(id={self.id}, code={self.code}, name={self.name}, price={self.price})>"


class PlanBase(BaseModel):
    code: str
    name: str
    description: Optional[str] = None
    price: int = 0
    currency: str = "MXN"
    interval: str = "month"
    stripe_price_id: Optional[str] = None
    analysis_limit: int = 2
    features: List[str] = []
    is_active: bool = True
    recommended: bool = False


class PlanCreate(PlanBase):
    pass


class PlanUpdate(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[int] = None
    currency: Optional[str] = None
    interval: Optional[str] = None
    stripe_price_id: Optional[str] = None
    analysis_limit: Optional[int] = None
    features: Optional[List[str]] = None
    is_active: Optional[bool] = None
    recommended: Optional[bool] = None


class PlanResponse(PlanBase):
    id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

    @classmethod
    def from_orm(cls, obj: Any):
        data = {
            "id": str(obj.id),
            "code": obj.code,
            "name": obj.name,
            "description": obj.description,
            "price": obj.price,
            "currency": obj.currency,
            "interval": obj.interval,
            "stripe_price_id": obj.stripe_price_id,
            "analysis_limit": obj.analysis_limit,
            "features": obj.features or [],
            "is_active": obj.is_active,
            "recommended": obj.recommended,
            "created_at": obj.created_at,
            "updated_at": obj.updated_at,
        }
        return cls(**data)
