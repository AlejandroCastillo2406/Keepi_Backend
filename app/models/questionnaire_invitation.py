import uuid
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field
from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


InvitationStatus = Literal["pending", "completed", "expired", "cancelled"]


class QuestionnaireInvitation(Base):
    __tablename__ = "questionnaire_invitations"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_questionnaire_invitation_token_hash"),
        CheckConstraint(
            "status IN ('pending','completed','expired','cancelled')",
            name="ck_questionnaire_invitation_status",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    doctor_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    token_hash = Column(String(128), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="pending", index=True)

    patient_email_snapshot = Column(String(255), nullable=False)
    patient_name_snapshot = Column(String(255), nullable=False)

    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    used_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    items = relationship(
        "QuestionnaireInvitationItem",
        back_populates="invitation",
        cascade="all, delete-orphan",
        order_by="QuestionnaireInvitationItem.sort_order.asc()",
    )


class QuestionnaireInvitationItem(Base):
    __tablename__ = "questionnaire_invitation_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    invitation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("questionnaire_invitations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_id = Column(
        UUID(as_uuid=True),
        ForeignKey("questionnaire_questions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    question_text_snapshot = Column(Text, nullable=False)
    response_type_snapshot = Column(String(20), nullable=False)
    options_snapshot = Column(JSONB, nullable=True)
    help_text_snapshot = Column(Text, nullable=True)
    is_required_snapshot = Column(Boolean, nullable=False, default=False)
    specialty_name_snapshot = Column(String(120), nullable=True)
    template_name_snapshot = Column(String(120), nullable=True)

    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    invitation = relationship("QuestionnaireInvitation", back_populates="items")
    answers = relationship(
        "QuestionnaireInvitationAnswer",
        back_populates="invitation_item",
        cascade="all, delete-orphan",
    )


class QuestionnaireInvitationAnswer(Base):
    __tablename__ = "questionnaire_invitation_answers"
    __table_args__ = (
        UniqueConstraint("invitation_item_id", name="uq_questionnaire_invitation_answer_item"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    invitation_item_id = Column(
        UUID(as_uuid=True),
        ForeignKey("questionnaire_invitation_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    answer_json = Column(JSONB, nullable=False)
    answered_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    invitation_item = relationship("QuestionnaireInvitationItem", back_populates="answers")


# ─────────────────────────────────────────────────────────────
# Schemas de apoyo para API pública y doctor
# ─────────────────────────────────────────────────────────────


class InvitationQuestionView(BaseModel):
    item_id: str
    question_text: str
    response_type: str
    options: Optional[List[str]] = None
    help_text: Optional[str] = None
    is_required: bool = False
    specialty_name: Optional[str] = None
    template_name: Optional[str] = None


class PublicInvitationViewResponse(BaseModel):
    invitation_id: str
    patient_name: str
    patient_email: str
    status: str
    expires_at: datetime
    questions: List[InvitationQuestionView] = Field(default_factory=list)


class PublicInvitationAnswerIn(BaseModel):
    item_id: str
    answer: Any


class PublicInvitationSubmitRequest(BaseModel):
    answers: List[PublicInvitationAnswerIn] = Field(default_factory=list)


class QuestionnaireSendInvitationRequest(BaseModel):
    patient_id: str
    template_ids: List[str] = Field(default_factory=list)
    question_ids: List[str] = Field(default_factory=list)
    expires_in_hours: int = 72


class QuestionnaireInvitationSummaryResponse(BaseModel):
    id: str
    doctor_id: str
    patient_id: str
    patient_name: str
    patient_email: str
    status: str
    created_at: datetime
    expires_at: datetime
    completed_at: Optional[datetime] = None
    total_questions: int = 0


class QuestionnaireInvitationSendResponse(BaseModel):
    invitation: QuestionnaireInvitationSummaryResponse
    public_link: str


class PublicInvitationSubmitResponse(BaseModel):
    invitation_id: str
    status: str
    completed_at: datetime
