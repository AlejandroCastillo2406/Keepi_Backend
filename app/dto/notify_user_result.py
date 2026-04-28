from __future__ import annotations

from dataclasses import dataclass

from app.services.notificaciones.payment_email_service import PaymentEmailResult


@dataclass
class NotifyUserResult:
    notification_id: str
    push_devices_ok: int


@dataclass
class NotifyUserWithEmailResult(NotifyUserResult):
    email: PaymentEmailResult
