class ArchivoTemporal:
    def __init__(self, id, nombre, ruta, usuario_id, token, expiracion):
        self.id = id
        self.nombre = nombre
        self.ruta = ruta
        self.usuario_id = usuario_id
        self.token = token
        self.expiracion = expiracion