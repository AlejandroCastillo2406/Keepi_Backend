#!/usr/bin/env python3
"""
Punto de entrada principal para la aplicación Keepi
"""

from app.main import app

if __name__ == "__main__":
    import uvicorn
    from app.config.settings import settings
    
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level="info"
    )