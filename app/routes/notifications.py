import logging
import os
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from app.core.security import require_no_temp_password_user
from app.factories.notification_factory import get_notification_service
from app.models.notification import NotificationCreate, NotificationResponse
from app.models.user import User
from app.services.notificaciones.notification_service import NotificationService

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/", response_model=list[NotificationResponse])
async def get_notifications(
    current_user: User = Depends(require_no_temp_password_user),
    notification_service: NotificationService = Depends(get_notification_service),
):
    try:
        return await notification_service.get_user_notifications(current_user.id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{notification_id}", response_model=NotificationResponse)
async def get_notification(
    notification_id: str,
    current_user: User = Depends(require_no_temp_password_user),
    notification_service: NotificationService = Depends(get_notification_service),
):
    try:
        notification = await notification_service.get_notification_by_id(
            notification_id, current_user.id
        )
        if notification:
            return notification
        raise HTTPException(status_code=404, detail="Notificación no encontrada")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/", response_model=NotificationResponse)
async def create_notification(
    notification_data: NotificationCreate,
    current_user: User = Depends(require_no_temp_password_user),
    notification_service: NotificationService = Depends(get_notification_service),
):
    try:
        return await notification_service.create_notification(
            current_user.id, notification_data
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{notification_id}")
async def delete_notification(
    notification_id: str,
    current_user: User = Depends(require_no_temp_password_user),
    notification_service: NotificationService = Depends(get_notification_service),
):
    try:
        success = await notification_service.delete_notification(
            notification_id, current_user.id
        )
        if success:
            return {
                "message": "Notificación eliminada correctamente",
                "notification_id": notification_id,
            }
        raise HTTPException(status_code=404, detail="Notificación no encontrada")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/payment-email")
async def send_payment_email(
    tipo: str,
    current_user: User = Depends(require_no_temp_password_user),
    notification_service: NotificationService = Depends(get_notification_service),
):
    try:
        return await notification_service.send_payment_email_by_type(
            current_user.id, tipo
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/run-expiry-emails")
def run_expiry_emails(
    days_before: int = 3,
    send_date: date | None = None,
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
    notification_service: NotificationService = Depends(get_notification_service),
):
    expected = os.getenv("EXPIRY_EMAIL_CRON_TOKEN")
    if not expected or x_internal_token != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")
    effective_send_date = send_date or datetime.now(timezone.utc).date()
    payload = notification_service.run_expiry_emails_job(
        send_date=effective_send_date, days_before=days_before
    )
    logger.info("run-expiry-emails OK")
    return payload


@router.post("/run-pill-reminders", summary="Run Pill Reminders")
async def run_pill_reminders(
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
    notification_service: NotificationService = Depends(get_notification_service),
):
    expected = os.getenv("EXPIRY_EMAIL_CRON_TOKEN")
    if not expected or x_internal_token != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        result = await notification_service.run_pill_reminders_job()
        logger.info("Pill reminders process completed")
        return result
    except Exception as e:
        logger.error("Error processing pill reminders: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/run-analysis-request-reminders")
def run_analysis_request_reminders(
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
    notification_service: NotificationService = Depends(get_notification_service),
):
    expected = os.getenv("EXPIRY_EMAIL_CRON_TOKEN")
    if not expected or x_internal_token != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")
    payload = notification_service.run_analysis_request_deadline_reminders_job()
    logger.info("run-analysis-request-reminders OK")
    return payload
