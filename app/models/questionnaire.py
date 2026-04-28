import uuid
from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base

QuestionOrigin = Literal["system", "custom"]
ResponseType = Literal[
    "single_choice",
    "multi_choice",
    "yes_no",
    "numeric",
    "short_text",
    "long_text",
]
QuestionStatusFilter = Literal["all", "active", "inactive"]


RESPONSE_TYPES: tuple[str, ...] = (
    "single_choice",
    "multi_choice",
    "yes_no",
    "numeric",
    "short_text",
    "long_text",
)


class Specialty(Base):
    __tablename__ = "questionnaire_specialties"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    slug = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(120), nullable=False)
    description = Column(Text, nullable=True)
    icon = Column(String(64), nullable=True)
    sort_order = Column(Integer, nullable=False, default=0, index=True)
    is_system = Column(Boolean, nullable=False, default=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    questions = relationship("Question", back_populates="specialty")


class Question(Base):
    __tablename__ = "questionnaire_questions"
    __table_args__ = (
        CheckConstraint(
            "origin IN ('system','custom')", name="ck_questionnaire_question_origin"
        ),
        CheckConstraint(
            "response_type IN ('single_choice','multi_choice','yes_no','numeric','short_text','long_text')",
            name="ck_questionnaire_question_response_type",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    specialty_id = Column(
        UUID(as_uuid=True),
        ForeignKey("questionnaire_specialties.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    owner_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    origin = Column(String(10), nullable=False, default="system", index=True)

    text = Column(Text, nullable=False)
    response_type = Column(String(20), nullable=False)

    options = Column(JSONB, nullable=True)
    help_text = Column(Text, nullable=True)

    is_required_default = Column(Boolean, nullable=False, default=False)
    show_in_history_default = Column(Boolean, nullable=False, default=True)
    is_active_default = Column(Boolean, nullable=False, default=True)

    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    specialty = relationship("Specialty", back_populates="questions")


class DoctorQuestionOverride(Base):
    __tablename__ = "questionnaire_doctor_overrides"
    __table_args__ = (
        UniqueConstraint(
            "doctor_id", "question_id", name="uq_doctor_question_override"
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    doctor_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_id = Column(
        UUID(as_uuid=True),
        ForeignKey("questionnaire_questions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    is_active = Column(Boolean, nullable=True)
    is_required = Column(Boolean, nullable=True)
    show_in_history = Column(Boolean, nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Template(Base):
    __tablename__ = "questionnaire_templates"
    __table_args__ = (
        UniqueConstraint("doctor_id", "name", name="uq_doctor_template_name"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    doctor_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    specialty_id = Column(
        UUID(as_uuid=True),
        ForeignKey("questionnaire_specialties.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name = Column(String(120), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    items = relationship(
        "TemplateQuestion",
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="TemplateQuestion.sort_order.asc()",
    )


class TemplateQuestion(Base):
    __tablename__ = "questionnaire_template_questions"
    __table_args__ = (
        UniqueConstraint("template_id", "question_id", name="uq_template_question"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    template_id = Column(
        UUID(as_uuid=True),
        ForeignKey("questionnaire_templates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_id = Column(
        UUID(as_uuid=True),
        ForeignKey("questionnaire_questions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    template = relationship("Template", back_populates="items")


class SpecialtyResponse(BaseModel):
    id: str
    slug: str
    name: str
    description: Optional[str] = None
    icon: Optional[str] = None
    sort_order: int = 0


class SpecialtySummary(SpecialtyResponse):
    total_questions: int = 0
    total_active: int = 0


class QuestionResponse(BaseModel):
    id: str
    specialty_id: Optional[str] = None
    specialty_name: Optional[str] = None
    origin: str
    owner_user_id: Optional[str] = None
    is_mine: bool = False

    text: str
    response_type: str
    options: Optional[List[str]] = None
    help_text: Optional[str] = None

    is_active: bool
    is_required: bool
    show_in_history: bool

    is_required_default: bool
    show_in_history_default: bool
    is_active_default: bool

    created_at: datetime
    updated_at: datetime


class QuestionCreateRequest(BaseModel):
    specialty_id: Optional[str] = None
    text: str = Field(..., min_length=3, max_length=500)
    response_type: str = Field(...)
    options: Optional[List[str]] = None
    help_text: Optional[str] = Field(default=None, max_length=500)
    is_required: bool = False
    show_in_history: bool = True

    @field_validator("response_type")
    @classmethod
    def _valid_response_type(cls, v: str) -> str:
        if v not in RESPONSE_TYPES:
            raise ValueError(f"Tipo de respuesta inválido: {v}")
        return v

    @field_validator("options")
    @classmethod
    def _options_clean(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return None
        cleaned = [o.strip() for o in v if o and o.strip()]
        return cleaned or None


class QuestionUpdateRequest(BaseModel):
    specialty_id: Optional[str] = None
    text: Optional[str] = Field(default=None, min_length=3, max_length=500)
    response_type: Optional[str] = None
    options: Optional[List[str]] = None
    help_text: Optional[str] = Field(default=None, max_length=500)
    is_required: Optional[bool] = None
    show_in_history: Optional[bool] = None

    @field_validator("response_type")
    @classmethod
    def _valid_response_type(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if v not in RESPONSE_TYPES:
            raise ValueError(f"Tipo de respuesta inválido: {v}")
        return v


class ToggleRequest(BaseModel):
    is_active: bool


class OverridesRequest(BaseModel):
    is_required: Optional[bool] = None
    show_in_history: Optional[bool] = None


class TemplateQuestionRef(BaseModel):
    id: str
    question_id: str
    sort_order: int


class TemplateResponse(BaseModel):
    id: str
    doctor_id: str
    specialty_id: Optional[str] = None
    specialty_name: Optional[str] = None
    name: str
    description: Optional[str] = None
    total_questions: int = 0
    created_at: datetime
    updated_at: datetime


class TemplateDetailResponse(TemplateResponse):
    questions: List[QuestionResponse] = Field(default_factory=list)


class TemplateCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    description: Optional[str] = Field(default=None, max_length=500)
    specialty_id: Optional[str] = None


class TemplateUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=120)
    description: Optional[str] = Field(default=None, max_length=500)
    specialty_id: Optional[str] = None


class TemplateQuestionsUpsertItem(BaseModel):
    question_id: str
    sort_order: int = 0


class TemplateQuestionsUpsertRequest(BaseModel):
    items: List[TemplateQuestionsUpsertItem] = Field(default_factory=list)
