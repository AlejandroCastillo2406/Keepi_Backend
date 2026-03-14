# Routes: definición de endpoints y orquestación de middlewares (solo los usados por el front)
from . import auth, cloud_storage, documents, subscriptions, user_config

__all__ = [
    "auth",
    "cloud_storage",
    "documents",
    "subscriptions",
    "user_config",
]
