import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import JSON, Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class OAuthCredentials(Base):
    __tablename__ = "oauth_credentials"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    provider = Column(String(50), nullable=False, default="google")
    access_token = Column(Text, nullable=False)
    refresh_token = Column(Text, nullable=True)
    token_uri = Column(
        String(255), nullable=False, default="https://oauth2.googleapis.com/token"
    )
    client_id = Column(String(255), nullable=True)
    client_secret = Column(String(255), nullable=True)
    scopes = Column(JSON, nullable=True, default=list)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user = relationship("User", back_populates="oauth_credentials")

    def __repr__(self):
        return f"<OAuthCredentials(id={self.id}, user_id={self.user_id}, provider={self.provider})>"


class OAuthCredentialsBase(BaseModel):
    user_id: str
    provider: str = "google"
    access_token: str
    refresh_token: Optional[str] = None
    token_uri: str = "https://oauth2.googleapis.com/token"
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    scopes: Optional[list] = None
    expires_at: Optional[datetime] = None


class OAuthCredentialsCreate(OAuthCredentialsBase):
    pass


class OAuthCredentialsUpdate(BaseModel):
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    expires_at: Optional[datetime] = None


class OAuthCredentialsResponse(OAuthCredentialsBase):
    id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

    @classmethod
    def from_orm(cls, obj):
        data = {
            "id": str(obj.id),
            "user_id": str(obj.user_id),
            "provider": obj.provider,
            "access_token": obj.access_token,
            "refresh_token": obj.refresh_token,
            "token_uri": obj.token_uri,
            "client_id": obj.client_id,
            "client_secret": obj.client_secret,
            "scopes": obj.scopes,
            "expires_at": obj.expires_at,
            "created_at": obj.created_at,
            "updated_at": obj.updated_at,
        }
        return cls(**data)
