from __future__ import annotations

from typing import Any, Dict, Optional, Protocol


class IArchivoService(Protocol):
    def subir_archivo(self, file: Any) -> Dict[str, str]: ...


class IRecetaArchivoProcesamientoService(Protocol):
    async def extraer_texto_y_receta(
        self,
        *,
        file_bytes: bytes,
        content_type: Optional[str],
        filename: Optional[str],
        doctor_email: str,
    ) -> Dict[str, Any]: ...

    def generar_url_presignada(
        self,
        file_key: str,
        tiempo_min: int = 60,
    ) -> Dict[str, Any]: ...
