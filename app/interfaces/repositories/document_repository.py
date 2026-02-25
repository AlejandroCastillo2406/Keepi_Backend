"""
Contrato del repositorio de documentos.
Permite sustituir la implementación por un mock en tests.
"""
from abc import ABC, abstractmethod
from typing import List, Optional

from pydantic import BaseModel


class IDocumentRepository(ABC):
    """Interfaz del repositorio de documentos. Solo acceso a datos."""

    @abstractmethod
    def get_by_user_id(self, user_id: str) -> List:
        """Lista todos los documentos del usuario. Retorna entidades ORM."""
        ...

    @abstractmethod
    def get_by_id(self, document_id: str, user_id: str) -> Optional[object]:
        """Obtiene un documento por id y user_id."""
        ...

    @abstractmethod
    def create(self, user_id: str, data: BaseModel) -> object:
        """Crea un documento. data: DocumentCreate (o compatible). Retorna entidad ORM."""
        ...

    @abstractmethod
    def update(
        self, document_id: str, user_id: str, data: BaseModel
    ) -> Optional[object]:
        """Actualiza un documento. data: DocumentUpdate (o compatible). Retorna ORM o None."""
        ...

    @abstractmethod
    def delete(self, document_id: str, user_id: str) -> bool:
        """Elimina un documento. Retorna True si existía y se eliminó."""
        ...
