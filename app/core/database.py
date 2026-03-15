"""Conexión y sesiones de PostgreSQL. Una sola responsabilidad."""
import logging
import uuid
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

logger = logging.getLogger(__name__)

Base = declarative_base()

# Límite por proceso: pool_size + max_overflow conexiones simultáneas a PostgreSQL.
# Con N workers (uvicorn/gunicorn): total máximo = N * (pool_size + max_overflow).
engine = create_engine(
    settings.database_url,
    echo=settings.echo_sql,
    pool_pre_ping=True,
    pool_recycle=settings.pool_recycle,
    pool_size=settings.pool_size,
    max_overflow=settings.pool_max_overflow,
    pool_timeout=settings.pool_timeout,
    connect_args={"options": "-c timezone=utc"},
)
logger.info(
    "DB pool: size=%s overflow=%s (max %s conexiones por proceso)",
    settings.pool_size,
    settings.pool_max_overflow,
    settings.pool_size + settings.pool_max_overflow,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class DatabaseConfig:
    _initialized = False

    @classmethod
    def initialize_database(cls) -> None:
        if cls._initialized:
            return
        try:
            from app.models import user, document, user_config, notification, folder, oauth_credentials, subscription  # noqa: F401
            Base.metadata.create_all(bind=engine)
            cls._initialized = True
            logger.info("Base de datos inicializada")
        except Exception as e:
            logger.exception("Error inicializando BD: %s", e)
            raise

    @classmethod
    def get_db_session(cls) -> Session:
        if not cls._initialized:
            cls.initialize_database()
        return SessionLocal()

    @classmethod
    def test_connection(cls) -> bool:
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception as e:
            logger.exception("Error conectando a PostgreSQL: %s", e)
            return False


def get_db() -> Generator[Session, None, None]:
    """Dependencia FastAPI: sesión de BD."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
