from fastapi import FastAPI
from fastapi.responses import HTMLResponse
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
from app.api.v1 import auth, documents, notifications, users, aws_documents, user_config, cloud_storage, test_flow, subscriptions

# Incluir routers
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(users.router, prefix="/api/v1/users", tags=["Users"])
app.include_router(documents.router, prefix="/api/v1/documents", tags=["Documents"])
app.include_router(notifications.router, prefix="/api/v1/notifications", tags=["Notifications"])
app.include_router(aws_documents.router, prefix="/api/v1/aws", tags=["AWS Documents"])
app.include_router(user_config.router, prefix="/api/v1/config", tags=["User Configuration"])
app.include_router(cloud_storage.router, prefix="/api/v1/cloud-storage", tags=["Cloud Storage"])
app.include_router(test_flow.router, prefix="/api/v1/test", tags=["Test Flow"])
app.include_router(subscriptions.router, prefix="/api/v1", tags=["Subscriptions & Payments"])

# Endpoints de pago fuera del prefix de API para URLs más limpias
@app.get("/payment/success")
async def payment_success(session_id: str):
    """Página de éxito después del pago en Stripe"""
    import stripe
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        logger.info(f"🎉 Pago exitoso - Session ID: {session_id}")
        
        # Verificar la sesión en Stripe
        session = stripe.checkout.Session.retrieve(session_id)
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Pago Exitoso - KIPI</title>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: Arial, sans-serif; text-align: center; padding: 50px; background: #f5f5f5; }}
                .container {{ background: white; padding: 40px; border-radius: 10px; max-width: 500px; margin: 0 auto; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
                .success {{ color: #28a745; font-size: 48px; margin-bottom: 20px; }}
                h1 {{ color: #333; }}
                p {{ color: #666; font-size: 18px; }}
                .btn {{ background: #007bff; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; display: inline-block; margin-top: 20px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="success">✅</div>
                <h1>¡Pago Exitoso!</h1>
                <p>Tu suscripción a KIPI Premium ha sido activada.</p>
                <p>Ahora puedes disfrutar de análisis ilimitados de documentos.</p>
                <p><strong>Plan:</strong> $49 MXN/mes</p>
                <p><small>Session ID: {session_id}</small></p>
                <a href="https://keepi.onrender.com" class="btn">Volver a KIPI</a>
            </div>
        </body>
        </html>
        """
        
        return HTMLResponse(content=html_content)
        
    except Exception as e:
        logger.error(f"❌ Error en página de éxito: {e}")
        error_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Error - KIPI</title>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: Arial, sans-serif; text-align: center; padding: 50px; background: #f5f5f5; }}
                .container {{ background: white; padding: 40px; border-radius: 10px; max-width: 500px; margin: 0 auto; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
                .error {{ color: #dc3545; font-size: 48px; margin-bottom: 20px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="error">❌</div>
                <h1>Error verificando el pago</h1>
                <p>Por favor contacta con soporte.</p>
            </div>
        </body>
        </html>
        """
        return HTMLResponse(content=error_html, status_code=500)

@app.get("/payment/cancel")
async def payment_cancel():
    """Página de cancelación del pago"""
    import logging
    logger = logging.getLogger(__name__)
    logger.info("❌ Pago cancelado por el usuario")
    
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Pago Cancelado - KIPI</title>
        <meta charset="UTF-8">
        <style>
            body { font-family: Arial, sans-serif; text-align: center; padding: 50px; background: #f5f5f5; }
            .container { background: white; padding: 40px; border-radius: 10px; max-width: 500px; margin: 0 auto; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
            .cancel { color: #dc3545; font-size: 48px; margin-bottom: 20px; }
            h1 { color: #333; }
            p { color: #666; font-size: 18px; }
            .btn { background: #007bff; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; display: inline-block; margin-top: 20px; margin: 10px; }
            .btn-secondary { background: #6c757d; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="cancel">❌</div>
            <h1>Pago Cancelado</h1>
            <p>No se procesó ningún cargo.</p>
            <p>Puedes intentar nuevamente cuando gustes.</p>
            <a href="https://keepi.onrender.com" class="btn">Volver a KIPI</a>
        </div>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html_content)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app, 
        host=settings.host, 
        port=settings.port,
        reload=settings.debug
    )
