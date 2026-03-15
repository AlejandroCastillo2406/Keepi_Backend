"""Configuración global de la aplicación (variables de entorno y constantes derivadas)."""
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

backend_dir = Path(__file__).resolve().parent.parent.parent
env_file = backend_dir / ".env"
if env_file.exists():
    load_dotenv(env_file)
else:
    load_dotenv()


class Settings(BaseSettings):
    """Configuración centralizada."""

    postgres_host: str = os.getenv("POSTGRES_HOST") or "localhost"
    postgres_port: int = int(os.getenv("POSTGRES_PORT") or "1234")
    postgres_db: str = os.getenv("POSTGRES_DB") or "db"
    postgres_user: str = os.getenv("POSTGRES_USER") or "user"
    postgres_password: str = os.getenv("POSTGRES_PASSWORD") or "password"

    @property
    def database_url(self) -> str:
        return f"postgresql://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

    # Pool de conexiones (por proceso). Total máx = pool_size + max_overflow.
    # En producción: ajustar según max_connections de PostgreSQL y número de workers.
    pool_size: int = int(os.getenv("DB_POOL_SIZE", "10"))
    pool_max_overflow: int = int(os.getenv("DB_POOL_MAX_OVERFLOW", "20"))
    pool_timeout: int = int(os.getenv("DB_POOL_TIMEOUT", "30"))
    pool_recycle: int = int(os.getenv("DB_POOL_RECYCLE", "300"))

    google_client_secrets_path: str = os.getenv("GOOGLE_CLIENT_SECRETS_PATH", "client_secrets.json")
    google_redirect_uri: Optional[str] = os.getenv("GOOGLE_REDIRECT_URI")

    api_title: str = "Keepi API"
    api_description: str = "API para el asistente inteligente de organización y gestión documental"
    api_version: str = "1.0.0"
    host: str = os.getenv("BACKEND_HOST") or "0.0.0.0"
    port: int = int(os.getenv("BACKEND_PORT") or "8000")
    debug: bool = os.getenv("DEBUG", "False").lower() == "true"

    cors_origins: list = ["*"]
    cors_allow_credentials: bool = True
    cors_allow_methods: list = ["*"]
    cors_allow_headers: list = ["*"]

    jwt_secret_key: str = os.getenv("JWT_SECRET_KEY") or "default-secret-key"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    max_file_size: int = 10 * 1024 * 1024  # 10MB
    allowed_file_types: list = [
        "image/jpeg", "image/png", "image/gif",
        "application/pdf", "text/plain",
        "application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ]

    cloudinary_cloud_name: str = os.getenv("CLOUDINARY_CLOUD_NAME", "")
    cloudinary_api_key: str = os.getenv("CLOUDINARY_API_KEY", "")
    cloudinary_api_secret: str = os.getenv("CLOUDINARY_API_SECRET", "")
    imgbb_api_key: str = os.getenv("IMGBB_API_KEY", "")

    aws_access_key_id: str = os.getenv("AWS_ACCESS_KEY_ID", "")
    aws_secret_access_key: str = os.getenv("AWS_SECRET_ACCESS_KEY", "")
    aws_region: str = os.getenv("AWS_REGION", "us-east-1")
    aws_s3_bucket: str = os.getenv("AWS_S3_BUCKET", "")

    stripe_secret_key: Optional[str] = None
    stripe_premium_price_id: Optional[str] = None
    stripe_webhook_secret: Optional[str] = None
    """URL de éxito de Stripe Checkout. Debe contener {CHECKOUT_SESSION_ID}. Definir STRIPE_PAYMENT_SUCCESS_URL en .env."""
    stripe_payment_success_url: Optional[str] = os.getenv("STRIPE_PAYMENT_SUCCESS_URL")
    """URL de cancelación de Stripe Checkout. Definir STRIPE_PAYMENT_CANCEL_URL en .env."""
    stripe_payment_cancel_url: Optional[str] = os.getenv("STRIPE_PAYMENT_CANCEL_URL")
    public_base_url: Optional[str] = os.getenv("PUBLIC_BASE_URL")

    echo_sql: bool = os.getenv("ECHO_SQL", "False").lower() == "true"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore",
    }


settings = Settings()
