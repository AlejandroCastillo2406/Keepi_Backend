import uuid
from sqlalchemy import Column, String, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

# Asegúrate de importar el Base de tu configuración (puede llamarse distinto en tu proyecto)
# Lo más común es algo como esto:
from app.core.database import Base # <-- Cambia esto si tu Base viene de otro lado

class QuestionnaireInvitation(Base):
    __tablename__ = "questionnaire_invitations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    doctor_id = Column(UUID(as_uuid=True), index=True)
    patient_id = Column(UUID(as_uuid=True), index=True)
    token_hash = Column(String, index=True)
    status = Column(String, default="pending")
    patient_email_snapshot = Column(String)
    patient_name_snapshot = Column(String)
    
    expires_at = Column(DateTime(timezone=True))
    used_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())