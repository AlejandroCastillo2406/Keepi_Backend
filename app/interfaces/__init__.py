from app.interfaces.archivo_repository_interface import IArchivoRepository
from app.interfaces.archivo_service_interface import (
    IArchivoService,
    IRecetaArchivoProcesamientoService,
)
from app.interfaces.document_interface import IDocumentRepository

__all__ = [
    "IDocumentRepository",
    "IArchivoRepository",
    "IArchivoService",
    "IRecetaArchivoProcesamientoService",
]
