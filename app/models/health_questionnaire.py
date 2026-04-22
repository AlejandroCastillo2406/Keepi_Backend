"""Catálogo de cuestionario de salud, preferencias por médico, envíos y respuestas (escalable)."""

import uuid
from datetime import datetime
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base

QuestionSection = Literal["general", "specialty"]
QuestionSource = Literal["seed", "doctor_custom"]
InitiationKind = Literal["onboarding_after_password", "doctor_manual"]


class HealthQuestionBank(Base):
    """Preguntas del banco (generales y por especialidad). source=doctor_custom reservado para futuro."""

    __tablename__ = "health_question_bank"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    section = Column(String(20), nullable=False, index=True)
    specialty_code = Column(String(64), nullable=True, index=True)
    specialty_label = Column(String(128), nullable=True)
    prompt = Column(Text, nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    source = Column(String(32), nullable=False, default="seed")
    created_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    visibility_overrides = relationship(
        "HealthQuestionDoctorVisibility",
        back_populates="question",
        cascade="all, delete-orphan",
    )


class HealthQuestionDoctorVisibility(Base):
    """Por médico: qué preguntas del banco mostrar u ocultar (ausencia de fila = visible por defecto)."""

    __tablename__ = "health_question_doctor_visibility"
    __table_args__ = (UniqueConstraint("doctor_user_id", "question_id", name="uq_health_q_visibility_doctor_question"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    doctor_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_id = Column(
        UUID(as_uuid=True),
        ForeignKey("health_question_bank.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    is_visible = Column(Boolean, nullable=False, default=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    question = relationship("HealthQuestionBank", back_populates="visibility_overrides")


class HealthQuestionnaireSubmission(Base):
    """Un envío del cuestionario (permite futuros reenvíos manuales por el médico)."""

    __tablename__ = "health_questionnaire_submissions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    patient_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    attending_doctor_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    initiation = Column(String(64), nullable=False, default="onboarding_after_password")
    template_version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    answers = relationship(
        "HealthQuestionnaireAnswer",
        back_populates="submission",
        cascade="all, delete-orphan",
    )


class HealthQuestionnaireAnswer(Base):
    __tablename__ = "health_questionnaire_answers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    submission_id = Column(
        UUID(as_uuid=True),
        ForeignKey("health_questionnaire_submissions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_id = Column(
        UUID(as_uuid=True),
        ForeignKey("health_question_bank.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    answer_text = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    submission = relationship("HealthQuestionnaireSubmission", back_populates="answers")


class PatientHealthCompletion(Base):
    """Estado de onboarding: primera vez que el paciente completó el cuestionario."""

    __tablename__ = "patient_health_questionnaire_completion"

    patient_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    last_submission_id = Column(
        UUID(as_uuid=True),
        ForeignKey("health_questionnaire_submissions.id", ondelete="SET NULL"),
        nullable=True,
    )
    completed_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


# --- DTOs API ---


class QuestionnaireQuestionOut(BaseModel):
    id: str
    prompt: str


class QuestionnaireSectionOut(BaseModel):
    title: str
    section: QuestionSection
    specialty_code: Optional[str] = None
    specialty_label: Optional[str] = None
    questions: List[QuestionnaireQuestionOut] = Field(default_factory=list)


class QuestionnaireForPatientResponse(BaseModel):
    completed: bool
    message: Optional[str] = None
    sections: List[QuestionnaireSectionOut] = Field(default_factory=list)


class QuestionnaireAnswerIn(BaseModel):
    question_id: str
    answer_text: str = Field(..., min_length=1, max_length=8000)


class QuestionnaireSubmitRequest(BaseModel):
    answers: List[QuestionnaireAnswerIn]


class DoctorQuestionSettingRow(BaseModel):
    question_id: str
    section: str
    specialty_code: Optional[str] = None
    specialty_label: Optional[str] = None
    prompt: str
    sort_order: int
    is_visible: bool
    has_doctor_override: bool


class DoctorQuestionnaireSettingsResponse(BaseModel):
    items: List[DoctorQuestionSettingRow]
    doctor_has_customization: bool


class DoctorVisibilityPatchItem(BaseModel):
    question_id: str
    is_visible: bool


class DoctorQuestionnaireSettingsPatchRequest(BaseModel):
    visibilities: List[DoctorVisibilityPatchItem]
