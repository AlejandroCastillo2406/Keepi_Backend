import uuid
from sqlalchemy import create_engine, MetaData, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
from app.config.settings import settings
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Base para modelos SQLAlchemy
Base = declarative_base()

# Metadata para manejo de esquemas
metadata = MetaData()

# Motor de base de datos
engine = create_engine(
    settings.database_url,
    echo=settings.echo_sql,
    pool_pre_ping=True,
    pool_recycle=300,
    connect_args={"options": "-c timezone=utc"}
)

# Factory de sesiones
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class DatabaseConfig:
    """Configuración de PostgreSQL"""
    
    _initialized = False
    
    @classmethod
    def initialize_database(cls):
        """Inicializar base de datos y crear tablas"""
        if cls._initialized:
            logger.info("Base de datos ya está inicializada")
            return
        
        try:
            # Importar todos los modelos para que se registren
            from app.models import user, document, ai_analysis, user_config, notification, folder, audit_log, backup_sync, search_index
            
            # Crear todas las tablas
            Base.metadata.create_all(bind=engine)
            logger.info("✅ Base de datos PostgreSQL inicializada correctamente")
            logger.info("✅ Todas las tablas creadas automáticamente")
            cls._initialized = True
            
        except Exception as e:
            logger.error(f"❌ Error inicializando base de datos: {e}")
            raise
    
    @classmethod
    def get_db_session(cls) -> Session:
        """Obtener sesión de base de datos"""
        if not cls._initialized:
            cls.initialize_database()
        return SessionLocal()
    
    @classmethod
    def close_db_session(cls, db: Session):
        """Cerrar sesión de base de datos"""
        try:
            db.close()
        except Exception as e:
            logger.error(f"Error cerrando sesión de BD: {e}")
    
    @classmethod
    def generate_uuid(cls) -> str:
        """Generar UUID único para IDs de usuario"""
        return str(uuid.uuid4())
    
    @classmethod
    def test_connection(cls) -> bool:
        """Probar conexión a la base de datos"""
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            logger.info("✅ Conexión a PostgreSQL exitosa")
            return True
        except Exception as e:
            logger.error(f"❌ Error conectando a PostgreSQL: {e}")
            return False

# Función para obtener sesión de BD (para dependency injection)
def get_db():
    """Dependency para obtener sesión de base de datos"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()