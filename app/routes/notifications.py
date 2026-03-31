import logging
import os
from datetime import date, datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_no_temp_password_token
from app.models.notification import NotificationCreate, NotificationResponse
from app.services.notificaciones.expiry_notification_service import (
    dispatch_expiry_emails,
)
from app.services.notificaciones import NotificationService
from app.services.notificaciones.payment_email_service import send_payment_email_ses
from app.services.usuarios.user_service import UserService

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/", response_model=List[NotificationResponse])
async def get_notifications(
    user_token: dict = Depends(require_no_temp_password_token),
    db: Session = Depends(get_db),
):
    """Obtener todas las notificaciones del usuario autenticado"""
    try:
        notification_service = NotificationService(db)
        notifications = await notification_service.get_user_notifications(user_token["uid"])
        return notifications
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{notification_id}", response_model=NotificationResponse)
async def get_notification(
    notification_id: str,
    user_token: dict = Depends(require_no_temp_password_token),
    db: Session = Depends(get_db),
):
    """Obtener notificación específica por ID"""
    try:
        notification_service = NotificationService(db)
        notification = await notification_service.get_notification_by_id(
            notification_id, user_token["uid"]
        )
        
        if notification:
            return notification
        else:
            raise HTTPException(status_code=404, detail="Notificación no encontrada")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/", response_model=NotificationResponse)
async def create_notification(
    notification_data: NotificationCreate,
    user_token: dict = Depends(require_no_temp_password_token),
    db: Session = Depends(get_db),
):
    """Crear nueva notificación"""
    try:
        notification_service = NotificationService(db)
        notification = await notification_service.create_notification(
            user_token["uid"], notification_data
        )
        return notification
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{notification_id}")
async def delete_notification(
    notification_id: str,
    user_token: dict = Depends(require_no_temp_password_token),
    db: Session = Depends(get_db),
):
    """Eliminar notificación"""
    try:
        notification_service = NotificationService(db)
        success = await notification_service.delete_notification(
            notification_id, user_token["uid"]
        )
        
        if success:
            return {"message": "Notificación eliminada correctamente", "notification_id": notification_id}
        else:
            raise HTTPException(status_code=404, detail="Notificación no encontrada")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/payment-email")
async def send_payment_email(
    tipo: str,
    user_token: dict = Depends(require_no_temp_password_token),
    db: Session = Depends(get_db),
):
    """
    Enviar correo de confirmación de pago o recordatorio de vencimiento.

    Parámetro `tipo`:
    - "confirmacion_pago"
    - "vencimiento"
    """
    if tipo not in {"confirmacion_pago", "vencimiento"}:
        raise HTTPException(
            status_code=400,
            detail="tipo debe ser 'confirmacion_pago' o 'vencimiento'",
        )

    user_service = UserService(db)
    user = await user_service.get_user_by_uid(user_token["uid"])
    if user is None or not user.email:
        raise HTTPException(status_code=400, detail="Usuario sin correo registrado")

    kind = "success" if tipo == "confirmacion_pago" else "vencimiento"
    result = send_payment_email_ses(
        to_email=user.email,
        kind=kind,
        user_name=user.name if hasattr(user, "name") else None,
    )

    if not result.success:
        raise HTTPException(status_code=502, detail=f"Error al enviar correo: {result.error}")

    return {"ok": True}


@router.post("/run-expiry-emails")
def run_expiry_emails(
    days_before: int = 3,
    send_date: date | None = None,
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
    db: Session = Depends(get_db),
):
    """
    Endpoint interno para que AWS (EventBridge/Lambda) dispare el envío de recordatorios
    por vencimiento. No autentica con JWT; usa `EXPIRY_EMAIL_CRON_TOKEN`.
    """
    expected = os.getenv("EXPIRY_EMAIL_CRON_TOKEN")
    if not expected or x_internal_token != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")

    effective_send_date = send_date or datetime.now(timezone.utc).date()
    result = dispatch_expiry_emails(db, send_date=effective_send_date, days_before=days_before)
    payload = result.to_dict()
    logger.info(
        "run-expiry-emails OK send_date=%s days_before=%s %s",
        effective_send_date,
        days_before,
        payload,
    )
    return payload
