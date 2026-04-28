from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.notification import (
    Notification,
    NotificationCreate,
    NotificationResponse,
)
from app.repositories.notification_repository import NotificationRepository
from app.dto.notify_user_result import NotifyUserResult


class NotificationService:

    def __init__(
        self,
        db: Session,
        notification_repository: NotificationRepository | None = None,
    ):
        self.db = db
        self._repo = notification_repository or NotificationRepository(db)

    async def get_user_notifications(self, user_id: Any) -> List[NotificationResponse]:
        notifications = self._repo.list_by_user(user_id)
        return [self._to_response(n) for n in notifications]

    async def get_notification_by_id(
        self, notification_id: str, user_id: Any
    ) -> Optional[NotificationResponse]:
        notification = self._repo.get_by_id_for_user(notification_id, user_id)
        if notification is None:
            return None
        return self._to_response(notification)

    async def create_notification(
        self, user_id: Any, notification_data: NotificationCreate
    ) -> NotificationResponse:
        notification = Notification(
            user_id=user_id,
            document_id=notification_data.document_id,
            title=notification_data.title,
            message=notification_data.message or notification_data.title,
            type=notification_data.type,
            target_date=notification_data.target_date,
            payload=notification_data.payload or {},
            read=notification_data.read or False,
            read_at=notification_data.read_at,
        )
        n = self._repo.add(notification)
        return self._to_response(n)

    async def delete_notification(self, notification_id: str, user_id: Any) -> bool:
        notification = self._repo.get_by_id_for_user(notification_id, user_id)
        if notification is None:
            return False
        self._repo.delete(notification)
        return True

    @staticmethod
    def _to_response(notification: Notification) -> NotificationResponse:
        return NotificationResponse(
            id=str(notification.id),
            user_id=str(notification.user_id),
            document_id=(
                str(notification.document_id) if notification.document_id else None
            ),
            title=notification.title,
            message=notification.message,
            type=notification.type,
            target_date=notification.target_date,
            payload=notification.payload or {},
            read=bool(notification.read),
            read_at=notification.read_at,
            created_at=notification.created_at,
        )

    def notify_user_push_in_app(
        self,
        user_id: Any,
        *,
        title: str,
        message: str,
        notification_type: str = "info",
        payload: Dict[str, Any] | None = None,
        document_id: Any | None = None,
        push_data: Dict[str, str] | None = None,
    ) -> NotifyUserResult:
        from uuid import UUID

        from app.services.notificaciones.fcm_push_service import send_push_to_user

        uid = UUID(str(user_id))
        doc_uuid = UUID(str(document_id)) if document_id is not None else None
        body_text = (message or "").strip() or title
        row = Notification(
            user_id=uid,
            document_id=doc_uuid,
            title=title,
            message=body_text,
            type=notification_type,
            payload=dict(payload or {}),
        )
        saved = self._repo.add(row)
        merged: dict[str, str] = {k: str(v) for k, v in (push_data or {}).items()}
        merged.setdefault("notification_id", str(saved.id))
        n_ok = send_push_to_user(
            db=self.db,
            user_id=str(uid),
            title=title,
            body=body_text,
            data=merged,
        )
        return NotifyUserResult(notification_id=str(saved.id), push_devices_ok=n_ok)

    def notify_questionnaire_completed_for_doctor(
        self,
        doctor_id: Any,
        *,
        patient_name: str,
        invitation_id: str,
        patient_id: str,
    ) -> None:
        title = "Cuestionario completado"
        message = f"{patient_name} completó su cuestionario de salud."
        self.notify_user_push_in_app(
            doctor_id,
            title=title,
            message=message,
            notification_type="info",
            payload={
                "type": "questionnaire_completed",
                "invitation_id": invitation_id,
                "patient_id": patient_id,
            },
            push_data={
                "type": "questionnaire_completed",
                "invitation_id": invitation_id,
                "patient_id": patient_id,
            },
        )

    async def send_payment_email_by_type(self, user_id: Any, tipo: str) -> dict:
        if tipo not in {"confirmacion_pago", "vencimiento"}:
            raise ValueError("tipo debe ser 'confirmacion_pago' o 'vencimiento'")
        from app.repositories.user_repository import UserRepository
        from app.services.notificaciones.payment_email_service import (
            send_payment_email_ses,
        )

        ur = UserRepository(self.db)
        user = ur.get_by_id_with_role(user_id)
        if user is None or not user.email:
            raise ValueError("Usuario sin correo registrado")
        kind = "success" if tipo == "confirmacion_pago" else "vencimiento"
        result = send_payment_email_ses(
            to_email=user.email,
            kind=kind,
            user_name=getattr(user, "name", None),
        )
        if not result.success:
            raise RuntimeError(result.error or "Error al enviar correo")
        return {"ok": True}

    def run_expiry_emails_job(self, *, send_date, days_before: int) -> dict:
        from app.services.notificaciones.expiry_notification_service import (
            dispatch_expiry_emails,
        )

        result = dispatch_expiry_emails(
            self.db, send_date=send_date, days_before=days_before
        )
        return result.to_dict()

    async def run_pill_reminders_job(self) -> Any:
        from app.services.notificaciones.pill_notification_service import (
            run_pill_reminders_process,
        )

        return await run_pill_reminders_process(self.db)
