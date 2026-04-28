import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel
from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class Folder(Base):
    __tablename__ = "folders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    name = Column(String(255), nullable=False)
    category = Column(String(100), nullable=False)
    parent_folder_id = Column(
        UUID(as_uuid=True), ForeignKey("folders.id"), nullable=True, index=True
    )
    drive_folder_id = Column(String(255), nullable=False)
    drive_parent_id = Column(String(255), nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user = relationship("User", back_populates="folders")
    documents = relationship("Document", back_populates="folder")
    parent_folder = relationship(
        "Folder", remote_side=[id], back_populates="subfolders"
    )
    subfolders = relationship("Folder", back_populates="parent_folder")

    def __repr__(self):
        return f"<Folder(id={self.id}, name={self.name}, category={self.category})>"


class FolderBase(BaseModel):
    name: str
    category: str
    parent_folder_id: Optional[str] = None


class FolderCreate(FolderBase):
    drive_folder_id: str
    drive_parent_id: Optional[str] = None


class FolderUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    parent_folder_id: Optional[str] = None


class FolderResponse(FolderBase):
    id: str
    user_id: str
    drive_folder_id: str
    drive_parent_id: Optional[str] = None
    documents_count: int = 0
    subfolders_count: int = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class FolderStructure(BaseModel):
    id: str
    name: str
    category: str
    drive_folder_id: str
    documents_count: int
    subfolders: List["FolderStructure"] = []
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


FolderStructure.model_rebuild()
