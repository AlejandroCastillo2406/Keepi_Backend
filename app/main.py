import logging
import os
from datetime import datetime
import stripe
import uvicorn
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import DatabaseConfig, get_db
from app.models.user_config import CloudProvider, UserConfigUpdate
from app.routes import (auth, cloud_storage, documents, notifications, subscriptions, user_config)
from app.routes.archivo_routes import router as archivo_router
from app.services.usuarios import UserConfigService

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger(__name__)

DatabaseConfig.initialize_database()

app = FastAPI(title=settings.api_title, debug=settings.debug)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# REGISTRO DE RUTAS
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(documents.router, prefix="/api/v1/documents", tags=["Documents"])
app.include_router(user_config.router, prefix="/api/v1/config", tags=["User Configuration"])
app.include_router(cloud_storage.router, prefix="/api/v1/cloud-storage", tags=["Cloud Storage"])
app.include_router(subscriptions.router, prefix="/api/v1", tags=["Subscriptions"])
app.include_router(notifications.router, prefix="/api/v1/notifications", tags=["Notifications"])

# --- AQUÍ ESTÁ TU RUTA DE ARCHIVOS ---
app.include_router(archivo_router, prefix="/api/v1/archivos", tags=["Archivos"])

@app.get("/")
async def root():
    return {"message": "Keepi API 🚀", "status": "running"}

# Manejador de errores
@app.exception_handler(404)
async def custom_404_handler(request: Request, exc):
    logger.error(f"❌ 404 en: {request.url}")
    return HTMLResponse(f"<h1>Ruta no encontrada: {request.url.path}</h1>", status_code=404)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True)