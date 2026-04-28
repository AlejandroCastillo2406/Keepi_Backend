from __future__ import annotations

import uuid
from datetime import date
from typing import Any, Optional

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.notifications_log import NotificationsLog


class NotificationsLogRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def try_insert_expiry_row(
        self,
        *,
        user_id: uuid.UUID,
        document_id: uuid.UUID,
        send_date: date,
        days_before: int,
        email_to: str,
    ) -> bool:
        stmt = pg_insert(NotificationsLog).values(
            user_id=user_id,
            document_id=document_id,
            notification_type="expiry",
            target_date=send_date,
            days_before=days_before,
            email_to=email_to,
            ses_message_id=None,
        )
        stmt = stmt.on_conflict_do_nothing(
            index_elements=[
                "user_id",
                "document_id",
                "notification_type",
                "target_date",
            ]
        )
        result = self._db.execute(stmt)
        inserted = int(getattr(result, "rowcount", 0) or 0) > 0
        if inserted:
            self._db.commit()
        return inserted

    def delete_expiry_row(
        self,
        *,
        user_id: uuid.UUID,
        document_id: uuid.UUID,
        send_date: date,
    ) -> None:
        self._db.query(NotificationsLog).filter(
            NotificationsLog.user_id == user_id,
            NotificationsLog.document_id == document_id,
            NotificationsLog.notification_type == "expiry",
            NotificationsLog.target_date == send_date,
        ).delete(synchronize_session=False)
        self._db.commit()

    def update_ses_message_id(
        self,
        *,
        user_id: uuid.UUID,
        document_id: uuid.UUID,
        send_date: date,
        ses_message_id: Optional[str],
    ) -> None:
        self._db.query(NotificationsLog).filter(
            NotificationsLog.user_id == user_id,
            NotificationsLog.document_id == document_id,
            NotificationsLog.notification_type == "expiry",
            NotificationsLog.target_date == send_date,
        ).update({"ses_message_id": ses_message_id}, synchronize_session=False)
        self._db.commit()
