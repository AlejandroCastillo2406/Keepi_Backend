import uuid

from sqlalchemy import Column, String
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class MedicalSpecialty(Base):
    __tablename__ = "medical_specialties"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    code = Column(String(64), unique=True, nullable=False, index=True)
    name_es = Column(String(255), nullable=False)

    def __repr__(self) -> str:
        return f"<MedicalSpecialty(code={self.code})>"
