class ArchivoRepository:

    def __init__(self, db):
        self.db = db

    def guardar(self, nombre, ruta, usuario_id, token, expiracion):
        cursor = self.db.cursor()
        cursor.execute("""
            INSERT INTO ARCHIVOS_TEMPORALES 
            (nombre_archivo, ruta_archivo, usuario_id, token_acceso, fecha_expiracion)
            VALUES (?, ?, ?, ?, ?)
        """, (nombre, ruta, usuario_id, token, expiracion))
        self.db.commit()

    def obtener_por_token(self, token):
        cursor = self.db.cursor()
        cursor.execute("""
            SELECT ruta_archivo, usuario_id, fecha_expiracion
            FROM ARCHIVOS_TEMPORALES
            WHERE token_acceso = ?
        """, (token,))
        return cursor.fetchone()