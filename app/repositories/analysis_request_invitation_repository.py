from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.analysis_request import AnalysisRequest
from app.models.analysis_request_invitation import AnalysisRequestUploadInvitation

INVITATION_TTL_DAYS = 30


class AnalysisRequestInvitationRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    @staticmethod
    def _hash_token(raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    @staticmethod
    def _generate_token() -> str:
        return secrets.token_urlsafe(32)

    def create_invitation(
        self,
        *,
        analysis_request: AnalysisRequest,
        patient_email: Optional[str],
        patient_name: Optional[str],
        ttl_days: int = INVITATION_TTL_DAYS,
        expires_at: Optional[datetime] = None,
    ) -> Tuple[AnalysisRequestUploadInvitation, str]:
        raw_token = self._generate_token()
        token_hash = self._hash_token(raw_token)
        
        if expires_at is not None:
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            final_expires_at = expires_at
        else:
            final_expires_at = datetime.now(timezone.utc) + timedelta(days=ttl_days)

        invitation = AnalysisRequestUploadInvitation(
            analysis_request_id=analysis_request.id,
            doctor_id=analysis_request.doctor_id,
            patient_id=analysis_request.patient_id,
            token_hash=token_hash,
            status="pending",
            patient_email_snapshot=(patient_email or "").strip() or None,
            patient_name_snapshot=(patient_name or "").strip() or None,
            expires_at=final_expires_at,
        )
        self._db.add(invitation)
        self._db.commit()
        self._db.refresh(invitation)
        return invitation, raw_token

    def get_for_public_token(
        self, raw_token: str
    ) -> Optional[AnalysisRequestUploadInvitation]:
        stripped = (raw_token or "").strip()
        if not stripped:
            return None
        token_hash = self._hash_token(stripped)
        inv = (
            self._db.query(AnalysisRequestUploadInvitation)
            .filter(AnalysisRequestUploadInvitation.token_hash == token_hash)
            .first()
        )
        if not inv:
            return None
        return self._mark_expired_if_needed(inv)

    def _mark_expired_if_needed(
        self, inv: AnalysisRequestUploadInvitation
    ) -> AnalysisRequestUploadInvitation:
        if inv.status != "pending":
            return inv
        expires_at = inv.expires_at
        if expires_at is None:
            return inv
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= datetime.now(timezone.utc):
            inv.status = "expired"
            self._db.commit()
            self._db.refresh(inv)
        return inv

    def mark_completed(
        self, invitation_id: UUID
    ) -> Optional[AnalysisRequestUploadInvitation]:
        inv = (
            self._db.query(AnalysisRequestUploadInvitation)
            .filter(AnalysisRequestUploadInvitation.id == invitation_id)
            .first()
        )
        if not inv:
            return None
        now = datetime.now(timezone.utc)
        inv.status = "completed"
        inv.used_at = now
        inv.completed_at = now
        self._db.commit()
        self._db.refresh(inv)
        return inv

    def cancel_pending_for_request(self, analysis_request_id: UUID) -> int:
        rows = (
            self._db.query(AnalysisRequestUploadInvitation)
            .filter(
                AnalysisRequestUploadInvitation.analysis_request_id
                == analysis_request_id,
                AnalysisRequestUploadInvitation.status == "pending",
            )
            .all()
        )
        for inv in rows:
            inv.status = "cancelled"
        self._db.commit()
        return len(rows)
