# Routes: definición de endpoints y orquestación de middlewares
from . import auth, aws_documents, cloud_storage, documents, notifications, subscriptions, user_config, users

__all__ = [
    "auth",
    "aws_documents",
    "cloud_storage",
    "documents",
    "notifications",
    "subscriptions",
    "user_config",
    "users",
]
