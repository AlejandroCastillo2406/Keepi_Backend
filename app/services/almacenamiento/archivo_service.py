import os
import uuid
from datetime import datetime, timedelta

from app.core.config import settings


class ArchivoService:

    def __init__(self, repo):
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

        self.repo.guardar(
            file.filename,
            ruta,
            token,
            expiracion
        )

        base_url = (settings.public_base_url or "").strip().rstrip("/")
        return {
            "url": f"{base_url}/api/v1/archivos/ver/{token}"
        }