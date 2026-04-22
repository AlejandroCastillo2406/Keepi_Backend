import logging
import os
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from app.core.config import settings
from app.core.database import DatabaseConfig

# Importación consolidada desde app.routes
from app.routes import (
    auth,
    cloud_storage,
    doctors,
    documents,
    notifications,
    patient,
    prescriptions,
    push_tokens,
    subscriptions,
    user_config,
    plans,
    analysis_request_routes, # <--- Ahora esto funcionará bien
    appointments,
    questionnaires,
)

from app.routes.archivo_routes import router as archivo_router

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

# REGISTRO DE RUTAS (CON PREFIJOS)
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(doctors.router, prefix="/api/v1/doctors", tags=["Doctors"])
app.include_router(patient.router, prefix="/api/v1/patient", tags=["Patient"])
app.include_router(documents.router, prefix="/api/v1/documents", tags=["Documents"])
app.include_router(user_config.router, prefix="/api/v1/config", tags=["User Configuration"])
app.include_router(cloud_storage.router, prefix="/api/v1/cloud-storage", tags=["Cloud Storage"])
app.include_router(notifications.router, prefix="/api/v1/notifications", tags=["Notifications"])
app.include_router(prescriptions.router, prefix="/api/v1/prescriptions", tags=["Prescriptions"])
app.include_router(push_tokens.router, prefix="/api/v1/push", tags=["Push"])
app.include_router(plans.router, prefix="/api/v1/plans", tags=["Admin Plans"])
app.include_router(subscriptions.router, prefix="/api/v1/subscriptions", tags=["Subscriptions"])
app.include_router(appointments.router, prefix="/api/v1/appointments", tags=["Appointments"])
app.include_router(questionnaires.router, prefix="/api/v1/questionnaires", tags=["Questionnaires"])

# Registro de la nueva ruta
app.include_router(
    analysis_request_routes.router, 
    prefix="/api/v1/analysis-requests", 
    tags=["Analysis Requests"]
)

app.include_router(
    archivo_router,
    prefix="/api/v1/archivos",
    tags=["Archivos Temporales"]
)

@app.get("/")
async def root():
    return {"message": "Keepi API 🚀", "status": "running"}

@app.exception_handler(404)
async def custom_404_handler(request: Request, exc):
    logger.error(f"❌ 404 en: {request.url}")
    return HTMLResponse(f"<h1>Ruta no encontrada: {request.url.path}</h1>", status_code=404)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True)