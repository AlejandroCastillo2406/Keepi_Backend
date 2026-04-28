from sqlalchemy import Column, String, DateTime, Integer
from app.core.database import Base


class SharedLink(Base):
    __tablename__ = "archivos_temporales"

    id = Column(Integer, primary_key=True, index=True)
    nombre_archivo = Column(String, nullable=False)
    ruta_archivo = Column(String, nullable=False)
    token_acceso = Column(String, unique=True, index=True)
    fecha_expiracion = Column(DateTime, nullable=False)
