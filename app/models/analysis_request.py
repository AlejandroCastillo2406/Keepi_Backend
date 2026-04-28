from sqlalchemy import Column, String, Text, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID
from app.config.database import Base
from datetime import datetime


class AnalysisRequest(Base):
    __tablename__ = "analysis_requests"
    __table_args__ = {"extend_existing": True}

    id = Column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    doctor_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    patient_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    description = Column(Text)
    status = Column(String(20))
    document_id = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    completed_at = Column(DateTime(timezone=True), nullable=True)
