import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from sqlalchemy.orm import relationship

from app.core.database import Base


class AppointmentPatientResponseToken(Base):
    __tablename__ = "appointment_patient_response_tokens"
    __table_args__ = (
        UniqueConstraint(
            "appointment_id",
            name="uq_appointment_patient_response_token_appointment",
        ),
        UniqueConstraint(
            "token_hash",
            name="uq_appointment_patient_response_token_hash",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    appointment_id = Column(
        UUID(as_uuid=True),
        ForeignKey("appointments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash = Column(String(128), nullable=False, index=True)
    response_action = Column(String(20), nullable=True)
    responded_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    appointment = relationship("Appointment", backref="patient_response_tokens")
