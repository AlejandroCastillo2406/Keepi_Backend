import os
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import boto3

from app.core.config import settings
from app.interfaces.archivo_repository_interface import IArchivoRepository
from app.services.ocr.textract_service import extract_text_from_document
from app.utils.prescription_cedula_parser import procesar_receta_con_seguridad


class RecetaArchivoProcesamientoService:

    def __init__(self) -> None:
        self._s3 = boto3.client(
            "s3",
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.aws_region,
        )

    async def extraer_texto_y_receta(
        self,
        *,
        file_bytes: bytes,
        content_type: Optional[str],
        filename: Optional[str],
        doctor_email: str,
        mantener_detalle_completo: bool = False,
    ) -> Dict[str, Any]:
        texto_raw = ""
        if content_type in ("image/jpeg", "image/png"):
            texto_raw = await extract_text_from_document(file_bytes=file_bytes)
        elif content_type == "application/pdf":
            temp_key = f"temp_ocr_{uuid.uuid4()}.pdf"
            self._s3.put_object(
                Bucket=settings.aws_s3_bucket,
                Key=temp_key,
                Body=file_bytes,
                ContentType="application/pdf",
            )
            texto_raw = await extract_text_from_document(
                s3_bucket=settings.aws_s3_bucket, s3_key=temp_key
            )
            self._s3.delete_object(Bucket=settings.aws_s3_bucket, Key=temp_key)
        else:
            raise ValueError("Formato no soportado.")
            
        resultados = procesar_receta_con_seguridad(texto_raw, mantener_detalle_completo)
        
        if resultados is None:
            raise PermissionError("RECETA_NO_VALIDA")
        return {
            "status": "success",
            "filename": filename,
            "doctor_autorizado": doctor_email,
            "recordatorios": resultados,
        }

    def generar_url_presignada(
        self, file_key: str, tiempo_min: int = 60
    ) -> Dict[str, Any]:
        try:
            url = self._s3.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": settings.aws_s3_bucket,
                    "Key": file_key,
                    "ResponseContentDisposition": "inline",
                },
                ExpiresIn=tiempo_min * 60,
            )
            return {"status": "success", "url": url}
        except Exception as e:
            return {"status": "error", "detail": str(e)}


class ArchivoService:

    def __init__(self, repo: IArchivoRepository):
        self.repo = repo
        self.upload_folder = "uploads"

        if not os.path.exists(self.upload_folder):
            os.makedirs(self.upload_folder)

    def subir_archivo(self, file):
        contenido = file.file.read()

        nombre_unico = str(uuid.uuid4()) + "_" + file.filename
        ruta = os.path.join(self.upload_folder, nombre_unico)

        with open(ruta, "wb") as f:
            f.write(contenido)

        token = str(uuid.uuid4())
        expiracion = datetime.now() + timedelta(minutes=10)

        self.repo.guardar(file.filename, ruta, token, expiracion)

        base_url = (settings.public_base_url or "").strip().rstrip("/")
        return {"url": f"{base_url}/api/v1/archivos/ver/{token}"}