import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.core.database import Base


class UserDeviceToken(Base):
    __tablename__ = "user_device_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    platform = Column(String(20), nullable=False, default="unknown")
    token = Column(String(1024), nullable=False, unique=True, index=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    last_seen_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class RegisterDeviceTokenRequest(BaseModel):
    token: str = Field(..., min_length=8)
    platform: str = "unknown"


class RegisterDeviceTokenResponse(BaseModel):
    ok: bool = True
    message: str = "Token registrado"
    token: str
    platform: str
    updated_at: Optional[datetime] = None

