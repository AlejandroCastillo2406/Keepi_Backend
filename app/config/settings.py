import os
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    """Configuración centralizada de la aplicación"""
    
    # PostgreSQL Configuration
    postgres_host: str = os.getenv("POSTGRES_HOST", "localhost")
    postgres_port: int = int(os.getenv("POSTGRES_PORT", "5432"))
    postgres_db: str = os.getenv("POSTGRES_DB", "keepi_db")
    postgres_user: str = os.getenv("POSTGRES_USER", "keepi_user")
    postgres_password: str = os.getenv("POSTGRES_PASSWORD", "Alex2406R")
    
    @property
    def database_url(self) -> str:
        """URL de conexión a PostgreSQL"""
        return f"postgresql://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
    
    # Google OAuth Configuration
    google_client_secrets_path: str = os.getenv("GOOGLE_CLIENT_SECRETS_PATH", "client_secrets.json")
    google_redirect_uri: Optional[str] = os.getenv("GOOGLE_REDIRECT_URI")
    
    # API Configuration
    api_title: str = "Keepi API"
    api_description: str = "API para el asistente inteligente de organización y gestión documental"
    api_version: str = "1.0.0"
    
    # Server Configuration
    host: str = os.getenv("BACKEND_HOST", "0.0.0.0")
    port: int = int(os.getenv("BACKEND_PORT", "8000"))
    debug: bool = os.getenv("DEBUG", "False").lower() == "true"
    
    # CORS Configuration
    cors_origins: list = ["*"]  # En producción, especificar dominios específicos
    cors_allow_credentials: bool = True
    cors_allow_methods: list = ["*"]
    cors_allow_headers: list = ["*"]
    
    # Security Configuration
    jwt_secret_key: str = os.getenv("JWT_SECRET_KEY", "your-super-secret-jwt-key-change-this-in-production")
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    
    # File Upload Configuration
    max_file_size: int = 10 * 1024 * 1024  # 10MB
    allowed_file_types: list = [
        "image/jpeg", "image/png", "image/gif", 
        "application/pdf", "text/plain", 
        "application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ]
    
    # Cloudinary Configuration
    cloudinary_cloud_name: str = os.getenv("CLOUDINARY_CLOUD_NAME", "")
    cloudinary_api_key: str = os.getenv("CLOUDINARY_API_KEY", "")
    cloudinary_api_secret: str = os.getenv("CLOUDINARY_API_SECRET", "")
    
    # ImgBB Configuration
    imgbb_api_key: str = os.getenv("IMGBB_API_KEY", "")
    
    # AWS Configuration
    aws_access_key_id: str = os.getenv("AWS_ACCESS_KEY_ID", "")
    aws_secret_access_key: str = os.getenv("AWS_SECRET_ACCESS_KEY", "")
    aws_region: str = os.getenv("AWS_REGION", "us-east-1")
    aws_s3_bucket: str = os.getenv("AWS_S3_BUCKET", "")
    
    # Database Configuration
    echo_sql: bool = os.getenv("ECHO_SQL", "False").lower() == "true"
    
    model_config = {
        "env_file": ".env",
        "case_sensitive": False,
        "extra": "ignore"
    }

# Instancia global de configuración
settings = Settings()
