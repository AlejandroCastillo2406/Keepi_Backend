from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from pydantic import Field, computed_field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

backend_dir = Path(__file__).resolve().parent.parent.parent
_env_path = backend_dir / ".env"
if _env_path.exists():
    load_dotenv(_env_path)
else:
    load_dotenv()


class Settings(BaseSettings):
    postgres_host: str = Field(default="localhost")
    postgres_port: int = Field(default=1234)
    postgres_db: str = Field(default="db")
    postgres_user: str = Field(default="user")
    postgres_password: str = Field(default="password")

    pool_size: int = Field(
        default=10, ge=1, description="Tamano del pool SQLAlchemy por proceso"
    )
    pool_max_overflow: int = Field(default=20, ge=0)
    pool_timeout: int = Field(default=30, ge=1)
    pool_recycle: int = Field(default=300, ge=60)

    google_client_secrets_path: str = Field(default="client_secrets.json")
    google_redirect_uri: Optional[str] = None

    api_title: str = "Keepi API"
    api_description: str = (
        "API para el asistente inteligente de organizacion y gestion documental"
    )
    api_version: str = "1.0.0"
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000, ge=1, le=65535)
    debug: bool = Field(default=False)

    cors_origins: list[str] = Field(default_factory=lambda: ["*"])
    cors_allow_credentials: bool = True
    cors_allow_methods: list[str] = Field(default_factory=lambda: ["*"])
    cors_allow_headers: list[str] = Field(default_factory=lambda: ["*"])

    jwt_secret_key: str = Field(default="default-secret-key", min_length=1)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = Field(default=30, ge=5)
    refresh_token_expire_days: int = Field(default=7, ge=1)

    max_file_size: int = Field(default=10 * 1024 * 1024, ge=1024)
    allowed_file_types: list[str] = Field(
        default_factory=lambda: [
            "image/jpeg",
            "image/png",
            "image/gif",
            "application/pdf",
            "text/plain",
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ]
    )

    cloudinary_cloud_name: str = ""
    cloudinary_api_key: str = ""
    cloudinary_api_secret: str = ""
    imgbb_api_key: str = ""

    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = "us-east-1"
    aws_s3_bucket: str = ""
    firebase_service_account_path: str = ""

    stripe_secret_key: Optional[str] = None
    stripe_premium_price_id: Optional[str] = None
    stripe_webhook_secret: Optional[str] = None
    stripe_payment_success_url: Optional[str] = None
    stripe_payment_cancel_url: Optional[str] = None
    public_base_url: Optional[str] = None
    archivos_public_base_url: Optional[str] = None
    public_questionnaire_base_url: Optional[str] = None

    echo_sql: bool = False

    # Si es False, el análisis de documentos no exige suscripción (desarrollo / transitorio).
    require_subscription_for_document_analysis: bool = Field(default=False)

    email_url_icon_check: str = ""
    email_url_icon_card: str = ""
    email_url_icon_vencimiento: str = ""
    email_url_footer_socials: str = ""
    email_link_account: str = ""
    email_link_help: str = ""
    email_support_address: str = ""
    email_brand_name: str = ""
    email_copyright_legal_name: str = ""
    email_placeholder_display_name: str = ""
    ses_from_email: str = ""
    ses_from_name: str = ""

    model_config = SettingsConfigDict(
        env_file=str(_env_path) if _env_path.exists() else ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("debug", "echo_sql", "require_subscription_for_document_analysis", mode="before")
    @classmethod
    def _parse_bool_fields(cls, v: Any) -> bool:
        if isinstance(v, bool):
            return v
        if v is None:
            return False
        return str(v).strip().lower() in ("1", "true", "yes", "on")

    @field_validator(
        "cors_origins", "cors_allow_methods", "cors_allow_headers", mode="before"
    )
    @classmethod
    def _split_csv_list(cls, v: Any) -> Any:
        if isinstance(v, str):
            parts = [p.strip() for p in v.split(",") if p.strip()]
            return parts if parts else ["*"]
        return v

    @model_validator(mode="after")
    def _reject_insecure_defaults_in_production(self) -> "Settings":
        if not self.debug and self.jwt_secret_key.strip() in ("", "default-secret-key"):
            raise ValueError(
                "Con DEBUG=false, JWT_SECRET_KEY debe estar definido y no puede ser 'default-secret-key'."
            )
        return self

    @computed_field
    @property
    def database_url(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @computed_field
    @property
    def firebase_service_account_path_resolved(self) -> str:
        raw = (self.firebase_service_account_path or "").strip()
        if not raw:
            return ""
        p = Path(raw)
        if p.is_absolute():
            return str(p.resolve())
        return str((backend_dir / p).resolve())


settings = Settings()
