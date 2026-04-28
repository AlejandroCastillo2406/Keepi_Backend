from __future__ import annotations

from datetime import datetime
from typing import Protocol


class IArchivoRepository(Protocol):
    def guardar(
        self,
        nombre: str,
        ruta: str,
        token: str,
        expiracion: datetime,
    ) -> None: ...

    def obtener_por_token(self, token: str) -> tuple[str, datetime] | None: ...
