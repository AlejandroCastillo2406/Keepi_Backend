import json
import logging
import uuid as uuid_lib
from pathlib import Path
from typing import Dict

from sqlalchemy.orm import Session

from app.core.config import settings
from app.repositories.user_device_token_repository import UserDeviceTokenRepository

logger = logging.getLogger(__name__)
_firebase_initialized = False


def _init_firebase() -> bool:
    global _firebase_initialized
    if _firebase_initialized:
        return True
    creds_path = getattr(
        settings,
        "firebase_service_account_path_resolved",
        "",
    ) or getattr(settings, "firebase_service_account_path", "")
    if not creds_path:
        logger.info("FCM desactivado: falta FIREBASE_SERVICE_ACCOUNT_PATH")
        return False
    if not Path(creds_path).exists():
        logger.warning("FCM desactivado: no existe %s", creds_path)
        return False
    try:
        import firebase_admin
        from firebase_admin import credentials

        if not firebase_admin._apps:
            firebase_admin.initialize_app(credentials.Certificate(creds_path))
        _firebase_initialized = True
        return True
    except Exception as exc:
        logger.warning("FCM no inicializado: %s", exc)
        return False


def send_push_to_user(
    db: Session, user_id: str, title: str, body: str, data: Dict[str, str] | None = None
) -> int:
    try:
        uid = uuid_lib.UUID(str(user_id).strip())
    except (ValueError, AttributeError):
        logger.warning("FCM: user_id inválido para push: %r", user_id)
        return 0

    tokens = UserDeviceTokenRepository(db).list_active_for_user(uid)
    if not tokens:
        logger.info(
            "FCM: ningún token activo para user_id=%s (la app debe registrar POST /api/v1/push/register tras login).",
            uid,
        )
        return 0
    if not _init_firebase():
        logger.warning(
            "FCM desactivado (falta JSON de cuenta de servicio o ruta inválida). Push no enviado. user_id=%s title=%s",
            uid,
            title,
        )
        return 0
    try:
        from firebase_admin import messaging

        payload_data = {k: str(v) for k, v in (data or {}).items()}
        ok = 0
        for t in tokens:
            msg = messaging.Message(
                token=t.token,
                notification=messaging.Notification(title=title, body=body),
                data=payload_data,
            )
            try:
                messaging.send(msg)
                ok += 1
            except Exception as exc:
                logger.warning("Error enviando push a token=%s: %s", t.id, exc)
        return ok
    except Exception as exc:
        logger.warning("Error general FCM: %s", exc)
        return 0


def build_reminder_prompt_payload(doctor_name: str) -> dict:
    return {
        "type": "prescription_assigned",
        "question": "Quieres que te recordemos cada que te toque la pastilla?",
        "doctor_name": doctor_name,
        "title": f"El doctor {doctor_name} te asigno una receta",
    }
