# Routes: definición de endpoints y orquestación de middlewares (solo los usados por el front)
from . import auth, plans, cloud_storage, doctors, documents, notifications, subscriptions, user_config

__all__ = [
    "auth",
    "doctors",
    "cloud_storage",
    "documents",
    "notifications",
    "subscriptions",
    "user_config",
    "plans",
]
