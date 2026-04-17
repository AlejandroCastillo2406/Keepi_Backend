from sqlalchemy import Column, String, Text, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime

# Importa la Base desde tu configuración de base de datos
# Ajusta esta ruta si tu archivo de base de datos está en otro lugar (ej. app.core.database)
from app.config.database import Base 

class AnalysisRequest(Base):
    __tablename__ = "analysis_requests"

    # ID autogenerado por Postgres usando gen_random_uuid()
    id = Column(
        UUID(as_uuid=True), 
        primary_key=True, 
        server_default=text("gen_random_uuid()")
    )

    # Relación con el Doctor (tabla users)
    doctor_id = Column(
        UUID(as_uuid=True), 
        ForeignKey("users.id", ondelete="CASCADE"), 
        nullable=False
    )

    # Relación con el Paciente (tabla users)
    patient_id = Column(
        UUID(as_uuid=True), 
        ForeignKey("users.id", ondelete="CASCADE"), 
        nullable=False
    )

    # Descripción de lo que se solicita
    description = Column(Text, nullable=False)

    # Estado: 'pending' por defecto
    status = Column(String(20), default="pending")

    # ID del documento vinculado (tabla documents)
    # Se llena cuando el paciente sube el archivo
    document_id = Column(
        UUID(as_uuid=True), 
        ForeignKey("documents.id", ondelete="SET NULL"), 
        nullable=True
    )

    # Tiempos de creación y completado
    created_at = Column(
        DateTime(timezone=True), 
        default=datetime.utcnow
    )
    
    completed_at = Column(
        DateTime(timezone=True), 
        nullable=True
    )

    # --- Opcional: Relaciones de SQLAlchemy (útil para hacer joins) ---
    doctor = relationship("User", foreign_keys=[doctor_id])
    patient = relationship("User", foreign_keys=[patient_id])
    document = relationship("Document", foreign_keys=[document_id])

    def __repr__(self):
        return f"<AnalysisRequest(id={self.id}, status={self.status}, patient={self.patient_id})>"