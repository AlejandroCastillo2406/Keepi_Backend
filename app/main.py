from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime

from app.config.settings import settings
from app.config.database import DatabaseConfig
from app.utils.auth import verify_token

# Inicializar PostgreSQL
DatabaseConfig.initialize_database()

# Crear aplicación FastAPI
app = FastAPI(
    title=settings.api_title,
    description=settings.api_description,
    version=settings.api_version,
    debug=settings.debug
)

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=settings.cors_allow_methods,
    allow_headers=settings.cors_allow_headers,
)

# Endpoints básicos
@app.get("/")
async def root():
    """Endpoint raíz"""
    return {
        "message": "Keepi API - Asistente Inteligente de Organización Documental",
        "version": settings.api_version,
        "status": "running"
    }

@app.get("/health")
async def health_check():
    """Endpoint de verificación de salud"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": settings.api_version
    }

# Importar routers
from app.api.v1 import auth, documents, notifications, users, aws_documents, user_config, cloud_storage, test_flow

# Incluir routers
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(users.router, prefix="/api/v1/users", tags=["Users"])
app.include_router(documents.router, prefix="/api/v1/documents", tags=["Documents"])
app.include_router(notifications.router, prefix="/api/v1/notifications", tags=["Notifications"])
app.include_router(aws_documents.router, prefix="/api/v1/aws", tags=["AWS Documents"])
app.include_router(user_config.router, prefix="/api/v1/config", tags=["User Configuration"])
app.include_router(cloud_storage.router, prefix="/api/v1/cloud-storage", tags=["Cloud Storage"])
app.include_router(test_flow.router, prefix="/api/v1/test", tags=["Test Flow"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app, 
        host=settings.host, 
        port=settings.port,
        reload=settings.debug
    )
