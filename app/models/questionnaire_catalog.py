"""Catálogo de cuestionarios diagnósticos: plantillas, versiones, preguntas y respuestas."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base

# scope: system_base | system_specialty | doctor_merged | doctor_custom
# template_type kept as string for flexibility


class QuestionnaireTemplate(Base):
    __tablename__ = "questionnaire_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    slug = Column(String(128), unique=True, nullable=False, index=True)
    scope = Column(String(32), nullable=False, index=True)
    owner_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    medical_specialty_id = Column(
        UUID(as_uuid=True),
        ForeignKey("medical_specialties.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title = Column(String(255), nullable=False, default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    versions = relationship(
        "QuestionnaireVersion",
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="QuestionnaireVersion.version.desc()",
    )


class QuestionnaireVersion(Base):
    __tablename__ = "questionnaire_versions"
    __table_args__ = (UniqueConstraint("template_id", "version", name="uq_qv_template_version"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    template_id = Column(
        UUID(as_uuid=True),
        ForeignKey("questionnaire_templates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version = Column(Integer, nullable=False, default=1)
    is_published = Column(Boolean, nullable=False, default=False)
    published_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    template = relationship("QuestionnaireTemplate", back_populates="versions")
    questions = relationship(
        "QuestionnaireQuestion",
        back_populates="version",
        cascade="all, delete-orphan",
        order_by="QuestionnaireQuestion.order_index",
    )


class QuestionnaireQuestion(Base):
    __tablename__ = "questionnaire_questions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    version_id = Column(
        UUID(as_uuid=True),
        ForeignKey("questionnaire_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    order_index = Column(Integer, nullable=False, default=0)
    section_key = Column(String(64), nullable=True)
    prompt = Column(Text, nullable=False)
    help_text = Column(Text, nullable=True)
    response_type = Column(String(64), nullable=False)
    config = Column(JSON, nullable=False, default=dict)

    version = relationship("QuestionnaireVersion", back_populates="questions")
    options = relationship(
        "QuestionnaireQuestionOption",
        back_populates="question",
        cascade="all, delete-orphan",
        order_by="QuestionnaireQuestionOption.order_index",
    )


class QuestionnaireQuestionOption(Base):
    __tablename__ = "questionnaire_question_options"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    question_id = Column(
        UUID(as_uuid=True),
        ForeignKey("questionnaire_questions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    value = Column(String(255), nullable=False)
    label = Column(String(512), nullable=False)
    icon_key = Column(String(64), nullable=True)
    order_index = Column(Integer, nullable=False, default=0)

    question = relationship("QuestionnaireQuestion", back_populates="options")


class DoctorQuestionnaireSettings(Base):
    __tablename__ = "doctor_questionnaire_settings"

    doctor_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    medical_specialty_id = Column(
        UUID(as_uuid=True),
        ForeignKey("medical_specialties.id", ondelete="SET NULL"),
        nullable=True,
    )
    mode = Column(String(32), nullable=False, default="system_composed")
    include_base_in_custom = Column(Boolean, nullable=False, default=True)
    active_version_id = Column(
        UUID(as_uuid=True),
        ForeignKey("questionnaire_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class QuestionnaireResponse(Base):
    __tablename__ = "questionnaire_responses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    version_id = Column(
        UUID(as_uuid=True),
        ForeignKey("questionnaire_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status = Column(String(20), nullable=False, default="draft")
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    created_by_doctor_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    answers = relationship(
        "QuestionnaireAnswer",
        back_populates="response",
        cascade="all, delete-orphan",
    )


class QuestionnaireAnswer(Base):
    __tablename__ = "questionnaire_answers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    response_id = Column(
        UUID(as_uuid=True),
        ForeignKey("questionnaire_responses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_id = Column(
        UUID(as_uuid=True),
        ForeignKey("questionnaire_questions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    value = Column(JSON, nullable=False, default=dict)

    response = relationship("QuestionnaireResponse", back_populates="answers")


# --- Pydantic ---


class QuestionOptionSchema(BaseModel):
    id: str
    value: str
    label: str
    icon_key: Optional[str] = None
    order_index: int = 0


class QuestionSchema(BaseModel):
    id: str
    order_index: int
    section_key: Optional[str] = None
    prompt: str
    help_text: Optional[str] = None
    response_type: str
    config: dict[str, Any] = Field(default_factory=dict)
    options: list[QuestionOptionSchema] = Field(default_factory=list)


class QuestionnaireRequiredResponse(BaseModel):
    required: bool
    version_id: Optional[str] = None
    response_id: Optional[str] = None
    status: Optional[str] = None
    title: str = ""
    questions: list[QuestionSchema] = Field(default_factory=list)


class DoctorQuestionnaireSettingsResponse(BaseModel):
    doctor_id: str
    medical_specialty_id: Optional[str] = None
    specialty_code: Optional[str] = None
    specialty_name: Optional[str] = None
    mode: str
    include_base_in_custom: bool
    active_version_id: Optional[str] = None


class DoctorQuestionnaireSettingsUpdate(BaseModel):
    medical_specialty_id: Optional[str] = None
    mode: Optional[str] = None
    include_base_in_custom: Optional[bool] = None


class PublishCustomBody(BaseModel):
    include_base: bool = True
    questions: list[dict[str, Any]] = Field(default_factory=list)
