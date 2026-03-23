import os
import uuid
from datetime import datetime, timedelta

class ArchivoService:

    def __init__(self, repo):
        self.repo = repo
        self.upload_folder = "uploads"

        # crear carpeta si no existe
        if not os.path.exists(self.upload_folder):
            os.makedirs(self.upload_folder)

    def subir_archivo(self, file, usuario_id):
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
            usuario_id,
            token,
            expiracion
        )

        return token

    def validar_archivo(self, token, usuario_id):
        archivo = self.repo.obtener_por_token(token)

        if not archivo:
            return None, "No existe"

        ruta, dueño_id, expiracion = archivo

        if usuario_id != dueño_id:
            return None, "No autorizado"

        if datetime.now() > expiracion:
            return None, "Expirado"

        return ruta, None