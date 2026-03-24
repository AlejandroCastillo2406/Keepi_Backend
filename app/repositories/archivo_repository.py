from sqlalchemy import text

class ArchivoRepository:

    def __init__(self, db):
        self.db = db

    def guardar(self, nombre, ruta, usuario_id, token, expiracion):
        self.db.execute(text("""
            INSERT INTO archivos_temporales 
            (nombre_archivo, ruta_archivo, usuario_id, token_acceso, fecha_expiracion)
            VALUES (:nombre, :ruta, :usuario_id, :token, :expiracion)
        """), {
            "nombre": nombre,
            "ruta": ruta,
            "usuario_id": usuario_id,
            "token": token,
            "expiracion": expiracion
        })

        self.db.commit()

    def obtener_por_token(self, token):
        result = self.db.execute(text("""
            SELECT ruta_archivo 
            FROM archivos_temporales
            WHERE token_acceso = :token
        """), {"token": token})

        row = result.fetchone()
        return row[0] if row else None