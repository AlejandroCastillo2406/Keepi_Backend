import logging
import os
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen

import stripe
import uvicorn
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import DatabaseConfig, get_db

# 🔥 IMPORTANTE: esto asegura que SQLAlchemy registre el modelo
from app.models.shared_link import SharedLink  # 👈 NO LO BORRES

from app.models.user_config import CloudProvider, UserConfigUpdate

from app.routes import (
    auth,
    cloud_storage,
    documents,
    notifications,
    subscriptions,
    user_config,
)

# 🔥 ARCHIVOS (TU SISTEMA SEGURO)
from app.routes.archivo_routes import router as archivo_router

from app.services.usuarios import UserConfigService


# 🔥 LOGS
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# 🔥 ENV
APP_DEEP_LINK_SUCCESS = os.getenv("APP_DEEP_LINK_SUCCESS")

CHECK_ORANGE_URL = os.getenv(
    "CHECK_ORANGE_URL",
    "https://res.cloudinary.com/dozavjhcx/image/upload/v1773901323/check_orange_xsnmqb.png",
)

BACKEND_DIR = Path(__file__).resolve().parent.parent


# 🔧 AUX
def _image_response(path: Path) -> Response:
    return Response(
        content=path.read_bytes(),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


# 🔥 INIT DB (CREA TABLAS)
DatabaseConfig.initialize_database()


# 🚀 APP
app = FastAPI(
    title=settings.api_title,
    description=settings.api_description,
    version=settings.api_version,
    debug=settings.debug,
)


# 🌐 CORS (PARA PRUEBAS OK)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # luego restringe en producción
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 🔥 ROUTERS BASE
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(documents.router, prefix="/api/v1/documents", tags=["Documents"])
app.include_router(user_config.router, prefix="/api/v1/config", tags=["User Configuration"])
app.include_router(cloud_storage.router, prefix="/api/v1/cloud-storage", tags=["Cloud Storage"])
app.include_router(subscriptions.router, prefix="/api/v1", tags=["Subscriptions & Payments"])
app.include_router(notifications.router, prefix="/api/v1/notifications", tags=["Notifications"])


# 🔥🔥 IMPORTANTE: ARCHIVOS SEGUROS (S3 + LINKS)
app.include_router(
    archivo_router,
    prefix="/api/v1/archivos",
    tags=["Archivos Temporales"]
)


# 🧪 ROOT
@app.get("/")
async def root():
    return {
        "message": "Keepi API funcionando 🚀",
        "version": settings.api_version,
        "status": "running",
    }


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
    }


# 🖼️ EMAIL ASSETS
@app.get("/email-assets/check_orange.png", include_in_schema=False)
async def email_check_orange():
    with urlopen(CHECK_ORANGE_URL) as response:
        return Response(
            content=response.read(),
            media_type=response.headers.get_content_type() or "image/png",
        )


@app.get("/email-assets/card_icon.png", include_in_schema=False)
async def email_card_icon():
    return _image_response(BACKEND_DIR / "assets/email/card_icon.png")


@app.get("/email-assets/vencimiento_icon.png", include_in_schema=False)
async def email_vencimiento_icon():
    return _image_response(BACKEND_DIR / "assets/email/vencimiento_icon.png")


@app.get("/email-assets/footer_socials.png", include_in_schema=False)
async def email_footer_socials():
    return _image_response(BACKEND_DIR / "assets/email/footer_socials.png")


# 💳 PAGOS
@app.get("/payment/success")
async def payment_success(session_id: str, db: Session = Depends(get_db)):
    try:
        session = stripe.checkout.Session.retrieve(session_id)

        if session.get("payment_status") == "paid":
            user_id = (session.metadata or {}).get("user_id")

            if user_id:
                config_service = UserConfigService(db)
                await config_service.get_or_create_user_config(user_id)

                await config_service.update_user_config(
                    user_id,
                    UserConfigUpdate(
                        cloud_provider=CloudProvider.KEEPI_CLOUD
                    )
                )

        return RedirectResponse(url=APP_DEEP_LINK_SUCCESS, status_code=302)

    except Exception:
        logger.exception("Error en pago")
        return HTMLResponse("<h1>Error en el pago</h1>", status_code=500)


@app.get("/payment/cancel")
async def payment_cancel():
    return HTMLResponse("""
    <html>
    <body style="text-align:center;padding:50px;">
        <h1>Pago Cancelado</h1>
    </body>
    </html>
    """)


# ▶️ RUN
if __name__ == "__main__":
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        reload=True
    )