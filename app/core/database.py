import logging
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

logger = logging.getLogger(__name__)

Base = declarative_base()


def _seed_roles_if_empty(session: Session) -> None:
    from app.core.roles import ROLE_DOCTOR, ROLE_PATIENT, ROLE_USER
    from app.repositories.role_repository import RoleRepository

    try:
        repo = RoleRepository(session)
        if repo.count_roles() > 0:
            return
        repo.add_role_rows((ROLE_DOCTOR, ROLE_USER, ROLE_PATIENT))
        session.commit()
        logger.info("Roles iniciales insertados (tabla roles estaba vacia)")
    except Exception as e:
        session.rollback()
        logger.debug("No se pudo sembrar roles: %s", e)


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
            from app.models import (
                analysis_request,
                analysis_request_invitation,
                appointment,
                document,
                folder,
                notification,
                notifications_log,
                oauth_credentials,
                prescription,
                questionnaire,
                questionnaire_invitation,
                role,
                subscription,
                user,
                user_config,
                user_device_token,
            )
            from app.core.seed_questionnaire import seed_questionnaire

            _ = (
                analysis_request,
                analysis_request_invitation,
                appointment,
                document,
                folder,
                notification,
                notifications_log,
                oauth_credentials,
                prescription,
                questionnaire,
                questionnaire_invitation,
                role,
                subscription,
                user,
                user_config,
                user_device_token,
            )
            Base.metadata.create_all(bind=engine)
            cls._apply_schema_patches()
            with SessionLocal() as db:
                _seed_roles_if_empty(db)
                seed_questionnaire(db)
            cls._initialized = True
            logger.info("Base de datos inicializada")
        except Exception as e:
            logger.exception("Error inicializando BD: %s", e)
            raise

    @classmethod
    def _apply_schema_patches(cls) -> None:
        """Migraciones ligeras idempotentes (columnas nuevas en tablas existentes)."""
        try:
            with engine.connect() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE questionnaire_invitations "
                        "ADD COLUMN IF NOT EXISTS collect_prior_documents "
                        "BOOLEAN NOT NULL DEFAULT FALSE"
                    )
                )
                conn.commit()
        except Exception as e:
            logger.warning("Schema patch questionnaire_invitations: %s", e)

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
    DatabaseConfig.initialize_database()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
