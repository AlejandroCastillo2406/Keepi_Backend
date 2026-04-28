from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.repositories.archivo_repository import ArchivoRepository
from app.services.almacenamiento.archivo_service import (
    ArchivoService,
    RecetaArchivoProcesamientoService,
)


def get_archivo_repository(db: Session = Depends(get_db)) -> ArchivoRepository:
    return ArchivoRepository(db)


def get_archivo_service(
    repo: ArchivoRepository = Depends(get_archivo_repository),
) -> ArchivoService:
    return ArchivoService(repo)


def get_receta_archivo_procesamiento_service() -> RecetaArchivoProcesamientoService:
    return RecetaArchivoProcesamientoService()
