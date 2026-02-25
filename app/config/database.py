# Re-export: usar app.core.database como fuente de verdad
from app.core.database import Base, DatabaseConfig, SessionLocal, engine, get_db

__all__ = ["Base", "DatabaseConfig", "SessionLocal", "engine", "get_db"]
