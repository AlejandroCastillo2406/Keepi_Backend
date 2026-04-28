import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, field_validator
from sqlalchemy import JSON, Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class UserConfig(Base):
    __tablename__ = "user_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        index=True,
        unique=True,
    )
    cloud_provider = Column(String(50), nullable=False, default="not_configured")
    notification_preferences = Column(JSON, nullable=True, default=dict)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user = relationship("User", back_populates="user_config")

    def __repr__(self):
        return f"<UserConfig(id={self.id}, user_id={self.user_id}, cloud_provider={self.cloud_provider})>"


class CloudProvider(str, Enum):
    NOT_CONFIGURED = "not_configured"
    GOOGLE_DRIVE = "google_drive"
    KEEPI_CLOUD = "keepi_cloud"


class UserConfigBase(BaseModel):
    cloud_provider: CloudProvider = CloudProvider.NOT_CONFIGURED
    notification_preferences: Optional[Dict[str, Any]] = None


class UserConfigCreate(UserConfigBase):
    pass


class UserConfigUpdate(BaseModel):
    cloud_provider: Optional[CloudProvider] = None
    notification_preferences: Optional[Dict[str, Any]] = None


class UserConfigResponse(UserConfigBase):
    id: str
    user_id: str
    created_at: datetime
    updated_at: datetime

    @field_validator("id", "user_id", mode="before")
    @classmethod
    def convert_uuid_to_str(cls, v):
        if isinstance(v, uuid.UUID):
            return str(v)
        return v

    class Config:
        from_attributes = True


class CloudProviderInfo(BaseModel):
    provider: CloudProvider
    name: str
    description: str
    features: list[str]
    storage_limit: Optional[str] = None
    is_available: bool = True
