import logging
import os
from datetime import datetime

import stripe
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.config import settings
from app.core.database import DatabaseConfig
from app.models.user_config import CloudProvider, UserConfigUpdate
from app.routes import auth, cloud_storage, documents, subscriptions, user_config
from app.services.usuarios import UserConfigService

logger = logging.getLogger(__name__)
APP_DEEP_LINK_SUCCESS = os.getenv("APP_DEEP_LINK_SUCCESS", "com.example.keepi://stripe-success")

DatabaseConfig.initialize_database()

app = FastAPI(
    title=settings.api_title,
    description=settings.api_description,
    version=settings.api_version,
    debug=settings.debug,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=settings.cors_allow_methods,
    allow_headers=settings.cors_allow_headers,
)

app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(documents.router, prefix="/api/v1/documents", tags=["Documents"])
app.include_router(user_config.router, prefix="/api/v1/config", tags=["User Configuration"])
app.include_router(cloud_storage.router, prefix="/api/v1/cloud-storage", tags=["Cloud Storage"])
app.include_router(subscriptions.router, prefix="/api/v1", tags=["Subscriptions & Payments"])


@app.get("/")
async def root():
    """Endpoint raíz"""
    return {
        "message": "Keepi API - Asistente Inteligente de Organización Documental",
        "version": settings.api_version,
        "status": "running",
    }


@app.get("/health")
async def health_check():
    """Endpoint de verificación de salud"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": settings.api_version,
    }


@app.get("/payment/success")
async def payment_success(session_id: str):
    """Tras el pago en Stripe: verifica sesión, pone keepi_cloud al usuario y redirige a la app."""
    try:
        logger.info("Pago exitoso - Session ID: %s", session_id)
        session = stripe.checkout.Session.retrieve(session_id)
        if session.get("payment_status") == "paid" and session.get("status") == "complete":
            user_id = (session.metadata or {}).get("user_id")
            if user_id:
                config_service = UserConfigService()
                await config_service.get_or_create_user_config(user_id)
                update_data = UserConfigUpdate(cloud_provider=CloudProvider.KEEPI_CLOUD)
                await config_service.update_user_config(user_id, update_data)
                logger.info("Usuario %s configurado a Keepi Cloud tras pago exitoso", user_id)
        return RedirectResponse(url=APP_DEEP_LINK_SUCCESS, status_code=302)
    except Exception:
        logger.exception("Error en página de éxito de pago")
        error_html = (
            "<!DOCTYPE html><html><head><title>Error - Keepi</title><meta charset=\"UTF-8\"></head>"
            "<body style=\"font-family: Arial; text-align: center; padding: 50px;\">"
            "<h1>Error verificando el pago</h1><p>Por favor contacta con soporte.</p>"
            "<a href=\"" + (settings.public_base_url or "") + "\">Volver a KIPI</a></body></html>"
        )
        return HTMLResponse(content=error_html, status_code=500)


@app.get("/payment/cancel")
async def payment_cancel():
    """Página de cancelación del pago"""
    logger.info("Pago cancelado por el usuario")
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Pago Cancelado - KIPI</title>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: Arial, sans-serif; text-align: center; padding: 50px; background: #f5f5f5; }}
            .container {{ background: white; padding: 40px; border-radius: 10px; max-width: 500px; margin: 0 auto; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
            .cancel {{ color: #dc3545; font-size: 48px; margin-bottom: 20px; }}
            h1 {{ color: #333; }}
            p {{ color: #666; font-size: 18px; }}
            .btn {{ background: #007bff; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; display: inline-block; margin-top: 20px; margin: 10px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="cancel">❌</div>
            <h1>Pago Cancelado</h1>
            <p>No se procesó ningún cargo.</p>
            <p>Puedes intentar nuevamente cuando gustes.</p>
            <a href="{settings.public_base_url or ''}" class="btn">Volver a KIPI</a>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


if __name__ == "__main__":
    uvicorn.run(app, host=settings.host, port=settings.port, reload=settings.debug)
