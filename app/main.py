import asyncio
import logging
import os
from contextlib import asynccontextmanager

import uvicorn
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse

from app.core.config import settings
from app.core.constants import (
    SCHEDULER_PILL_JOB_ID,
    SCHEDULER_PILL_REMINDER_INTERVAL_HOURS,
)
from app.core.database import DatabaseConfig, SessionLocal
from app.routes import (
    analysis_request_routes,
    appointments,
    auth,
    cloud_storage,
    doctors,
    documents,
    notifications,
    patient,
    plans,
    prescriptions,
    push_tokens,
    questionnaire,
    subscriptions,
    user_config,
)
from app.routes.archivo_routes import router as archivo_router
from app.services.notificaciones.pill_notification_service import (
    run_pill_reminders_process,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger(__name__)


def _run_pill_reminders_sync() -> None:
    db = SessionLocal()
    try:
        result = asyncio.run(run_pill_reminders_process(db))
        logger.info("Pill reminder job completed: %s", result)
    except Exception:
        logger.exception("Pill reminder job failed")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    DatabaseConfig.initialize_database()
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        _run_pill_reminders_sync,
        "interval",
        hours=SCHEDULER_PILL_REMINDER_INTERVAL_HOURS,
        id=SCHEDULER_PILL_JOB_ID,
        replace_existing=True,
    )
    scheduler.start()
    logger.info(
        "Scheduler started: pill reminders every %s h",
        SCHEDULER_PILL_REMINDER_INTERVAL_HOURS,
    )
    yield
    scheduler.shutdown(wait=False)
    logger.info("Scheduler stopped")


app = FastAPI(
    title=settings.api_title,
    description=settings.api_description,
    version=settings.api_version,
    debug=settings.debug,
    lifespan=lifespan,
)


@app.exception_handler(StarletteHTTPException)
async def starlette_http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    if exc.status_code != 404:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": jsonable_encoder(exc.detail)},
        )
    logger.warning("Not found: %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=404,
        content={
            "detail": "not_found",
            "path": request.url.path,
        },
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=settings.cors_allow_methods,
    allow_headers=settings.cors_allow_headers,
)

app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(doctors.router, prefix="/api/v1/doctors", tags=["Doctors"])
app.include_router(patient.router, prefix="/api/v1/patient", tags=["Patient"])
app.include_router(documents.router, prefix="/api/v1/documents", tags=["Documents"])
app.include_router(
    user_config.router, prefix="/api/v1/config", tags=["User Configuration"]
)
app.include_router(
    cloud_storage.router, prefix="/api/v1/cloud-storage", tags=["Cloud Storage"]
)
app.include_router(
    notifications.router, prefix="/api/v1/notifications", tags=["Notifications"]
)
app.include_router(
    prescriptions.router, prefix="/api/v1/prescriptions", tags=["Prescriptions"]
)
app.include_router(push_tokens.router, prefix="/api/v1/push", tags=["Push"])
app.include_router(plans.router, prefix="/api/v1/admin/plans", tags=["Admin Plans"])
app.include_router(
    subscriptions.router, prefix="/api/v1/subscriptions", tags=["Subscriptions"]
)
app.include_router(
    appointments.router, prefix="/api/v1/appointments", tags=["Appointments"]
)
app.include_router(
    questionnaire.router, prefix="/api/v1/questionnaire", tags=["Questionnaire"]
)
app.include_router(
    analysis_request_routes.router,
    prefix="/api/v1/analysis-requests",
    tags=["Analysis Requests"],
)
app.include_router(
    archivo_router,
    prefix="/api/v1/archivos",
    tags=["Archivos Temporales"],
)


@app.get("/")
async def root():
    from app.services.api_info_service import ApiInfoService

    return ApiInfoService.root_payload()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", settings.port))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True)
