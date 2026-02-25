# Re-export: usar app.core.config como fuente de verdad
from app.core.config import Settings, settings

__all__ = ["Settings", "settings"]
