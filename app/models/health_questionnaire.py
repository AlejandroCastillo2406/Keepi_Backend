"""Catálogo de cuestionario de salud, preferencias por médico, envíos y respuestas.

Modelo extendido para el flujo nuevo del doctor (pantallas de cuestionario con especialidades,
plantillas personalizadas, preguntas globales y tipos de respuesta variados).

Columnas nuevas se añaden en BD vía migración ligera en `app.services.health_questionnaire_service`.
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import (
    Boolean,
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

# ---------------------------------------------------------------------------
# Tipado
# ---------------------------------------------------------------------------

# `section` se mantiene para compatibilidad con filas históricas:
#   - "general"  = pregunta global (specialty_code is NULL)
#   - "specialty" = pregunta ligada a una especialidad
QuestionSection = Literal["general", "specialty"]
QuestionSource = Literal["seed", "doctor_custom"]
QuestionType = Literal[
    "single_choice",
    "multi_choice",
    "yes_no",
    "numeric",
    "short_text",
    "long_text",
]
InitiationKind = Literal["onboarding_after_password", "doctor_manual"]


# ---------------------------------------------------------------------------
# Tablas
# ---------------------------------------------------------------------------


class HealthSpecialty(Base):
    """Catálogo fijo de especialidades mostradas en la UI del doctor."""

    __tablename__ = "health_specialty"

    code = Column(String(64), primary_key=True)
    label = Column(String(128), nullable=False)
    description = Column(String(255), nullable=True)
    icon_key = Column(String(64), nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class HealthQuestionBank(Base):
    """Preguntas del banco.

    - source="seed" y owner_doctor_user_id IS NULL: preguntas oficiales de Keepi.
    - source="doctor_custom" y owner_doctor_user_id=<doctor>: preguntas creadas por ese doctor.
    - specialty_code IS NULL: pregunta "global" (aplica a cualquier paciente del doctor).
    """

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
    # owner_doctor_user_id: propietario lógico de la pregunta (doctor que la creó). Distinto de
    # created_by_user_id en que, para preguntas seed de Keepi, queda NULL aunque un admin las
    # haya insertado. Se usa para filtrar "mis preguntas vs las de Keepi".
    owner_doctor_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    question_type = Column(String(32), nullable=False, default="short_text")
    options = Column(JSONB, nullable=True)  # lista de strings para single/multi choice
    is_required = Column(Boolean, nullable=False, default=True)
    show_in_history = Column(Boolean, nullable=False, default=True)
    help_text = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    visibility_overrides = relationship(
        "HealthQuestionDoctorVisibility",
        back_populates="question",
        cascade="all, delete-orphan",
    )


class HealthQuestionDoctorVisibility(Base):
    """Por médico: qué preguntas del banco mostrar u ocultar.

    Solo tiene sentido para preguntas de Keepi (owner NULL) y para preguntas de otros doctores
    (no deberían existir). Para las preguntas propias del doctor se usa `is_active`.
    """

    __tablename__ = "health_question_doctor_visibility"
    __table_args__ = (
        UniqueConstraint("doctor_user_id", "question_id", name="uq_health_q_visibility_doctor_question"),
    )

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
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    question = relationship("HealthQuestionBank", back_populates="visibility_overrides")


class HealthQuestionnaireTemplate(Base):
    """Plantillas personalizadas del doctor (set de preguntas asignable a pacientes puntuales)."""

    __tablename__ = "health_questionnaire_template"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    doctor_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(160), nullable=False)
    description = Column(String(300), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    questions = relationship(
        "HealthQuestionnaireTemplateQuestion",
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="HealthQuestionnaireTemplateQuestion.sort_order",
    )
    assignments = relationship(
        "HealthQuestionnaireTemplateAssignment",
        back_populates="template",
        cascade="all, delete-orphan",
    )


class HealthQuestionnaireTemplateQuestion(Base):
    __tablename__ = "health_questionnaire_template_question"
    __table_args__ = (
        UniqueConstraint("template_id", "question_id", name="uq_tpl_question_unique"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id = Column(
        UUID(as_uuid=True),
        ForeignKey("health_questionnaire_template.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_id = Column(
        UUID(as_uuid=True),
        ForeignKey("health_question_bank.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sort_order = Column(Integer, nullable=False, default=0)

    template = relationship("HealthQuestionnaireTemplate", back_populates="questions")
    question = relationship("HealthQuestionBank")


class HealthQuestionnaireTemplateAssignment(Base):
    """Asignación de plantilla a paciente (override del cuestionario por especialidad)."""

    __tablename__ = "health_questionnaire_template_assignment"
    __table_args__ = (
        UniqueConstraint("template_id", "patient_user_id", name="uq_tpl_assignment_unique"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id = Column(
        UUID(as_uuid=True),
        ForeignKey("health_questionnaire_template.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    patient_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    template = relationship("HealthQuestionnaireTemplate", back_populates="assignments")


class HealthQuestionnaireSubmission(Base):
    """Un envío del cuestionario."""

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
    template_id = Column(
        UUID(as_uuid=True),
        ForeignKey("health_questionnaire_template.id", ondelete="SET NULL"),
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
    # answer_text queda como representación legible/legacy (siempre presente para retrocompat).
    answer_text = Column(Text, nullable=False, default="")
    # answer_value guarda el valor tipado:
    #   - single_choice / short_text / long_text / yes_no: string
    #   - multi_choice: list[str]
    #   - numeric: number
    answer_value = Column(JSONB, nullable=True)
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
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


# ---------------------------------------------------------------------------
# DTOs API – paciente (cuestionario para llenar)
# ---------------------------------------------------------------------------


class QuestionnaireQuestionOut(BaseModel):
    id: str
    prompt: str
    question_type: QuestionType = "short_text"
    options: Optional[List[str]] = None
    is_required: bool = True
    help_text: Optional[str] = None


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
    template_id: Optional[str] = None
    template_name: Optional[str] = None


class QuestionnaireAnswerIn(BaseModel):
    question_id: str
    # Valor tipado. Para retrocompat sigue aceptándose string puro.
    answer_value: Any = None
    answer_text: Optional[str] = Field(default=None, max_length=8000)


class QuestionnaireSubmitRequest(BaseModel):
    answers: List[QuestionnaireAnswerIn]


# ---------------------------------------------------------------------------
# DTOs API – doctor (gestión del cuestionario)
# ---------------------------------------------------------------------------


class SpecialtyOut(BaseModel):
    code: str
    label: str
    description: Optional[str] = None
    icon_key: Optional[str] = None
    sort_order: int = 0
    total: int = 0
    active: int = 0
    inactive: int = 0


class SpecialtiesListResponse(BaseModel):
    specialties: List[SpecialtyOut]
    global_total: int = 0
    global_active: int = 0
    global_inactive: int = 0


class DoctorQuestionOut(BaseModel):
    id: str
    prompt: str
    specialty_code: Optional[str] = None
    specialty_label: Optional[str] = None
    question_type: QuestionType
    options: Optional[List[str]] = None
    is_required: bool
    show_in_history: bool
    help_text: Optional[str] = None
    is_active: bool  # visible para pacientes del doctor
    is_owned_by_doctor: bool  # True => creada por el doctor; False => pregunta de Keepi
    sort_order: int


class DoctorQuestionListResponse(BaseModel):
    items: List[DoctorQuestionOut]
    total: int
    active: int
    inactive: int


class DoctorQuestionCreateRequest(BaseModel):
    prompt: str = Field(..., min_length=3, max_length=500)
    specialty_code: Optional[str] = None  # None => global
    question_type: QuestionType
    options: Optional[List[str]] = None
    is_required: bool = True
    show_in_history: bool = True
    help_text: Optional[str] = Field(default=None, max_length=500)

    @field_validator("options")
    @classmethod
    def _validate_options(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return v
        cleaned = [str(x).strip() for x in v if str(x).strip()]
        return cleaned or None


class DoctorQuestionUpdateRequest(BaseModel):
    prompt: Optional[str] = Field(default=None, min_length=3, max_length=500)
    specialty_code: Optional[str] = None
    question_type: Optional[QuestionType] = None
    options: Optional[List[str]] = None
    is_required: Optional[bool] = None
    show_in_history: Optional[bool] = None
    help_text: Optional[str] = Field(default=None, max_length=500)
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class DoctorQuestionReorderItem(BaseModel):
    question_id: str
    sort_order: int


class DoctorQuestionReorderRequest(BaseModel):
    items: List[DoctorQuestionReorderItem]


# --- Plantillas personalizadas ---


class TemplateQuestionOut(BaseModel):
    question_id: str
    prompt: str
    question_type: QuestionType
    specialty_code: Optional[str] = None
    specialty_label: Optional[str] = None
    sort_order: int


class TemplateOut(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    questions_count: int
    assigned_count: int
    created_at: datetime


class TemplateDetailOut(TemplateOut):
    questions: List[TemplateQuestionOut] = Field(default_factory=list)
    assigned_patient_ids: List[str] = Field(default_factory=list)


class TemplateListResponse(BaseModel):
    templates: List[TemplateOut]


class TemplateCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=160)
    description: Optional[str] = Field(default=None, max_length=300)
    question_ids: List[str] = Field(default_factory=list)


class TemplateUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=160)
    description: Optional[str] = Field(default=None, max_length=300)
    question_ids: Optional[List[str]] = None


class TemplateAssignRequest(BaseModel):
    patient_user_ids: List[str] = Field(default_factory=list)


# --- Legacy DTOs (se conservan para no romper imports existentes) ---


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
