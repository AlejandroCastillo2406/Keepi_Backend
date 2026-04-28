from sqlalchemy import text


class ArchivoRepository:

    def __init__(self, db):
        self.db = db

    def guardar(self, nombre, ruta, token, expiracion):
        self.db.execute(
            text("""
            INSERT INTO archivos_temporales 
            (nombre_archivo, ruta_archivo, token_acceso, fecha_expiracion)
            VALUES (:nombre, :ruta, :token, :expiracion)
        """),
            {"nombre": nombre, "ruta": ruta, "token": token, "expiracion": expiracion},
        )

        self.db.commit()

    def obtener_por_token(self, token):
        result = self.db.execute(
            text("""
            SELECT ruta_archivo, fecha_expiracion
            FROM archivos_temporales
            WHERE token_acceso = :token
        """),
            {"token": token},
        )

        row = result.fetchone()

        if row:
            return row[0], row[1]

        return None
