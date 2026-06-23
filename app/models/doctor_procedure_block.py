import uuid
from datetime import datetime
from typing import List, Optional
from uuid import UUID as PyUUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.sql import func

from app.core.database import Base


class DoctorProcedureBlock(Base):
    __tablename__ = "doctor_procedure_blocks"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    doctor_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title = Column(String(200), nullable=False, default="")
    start_at = Column(DateTime(timezone=True), nullable=False, index=True)
    end_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ProcedureBlockCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    start_at: datetime
    end_at: datetime


class ProcedureBlockResponse(BaseModel):
    id: PyUUID
    doctor_id: PyUUID
    title: str
    start_at: datetime
    end_at: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, arbitrary_types_allowed=True)

    @classmethod
    def from_entity(cls, row: DoctorProcedureBlock) -> "ProcedureBlockResponse":
        return cls(
            id=row.id,
            doctor_id=row.doctor_id,
            title=row.title or "",
            start_at=row.start_at,
            end_at=row.end_at,
            created_at=row.created_at,
        )
