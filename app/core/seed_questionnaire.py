"""Seed inicial de especialidades y preguntas base del sistema.

Idempotente: solo inserta si las tablas correspondientes están vacías.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.questionnaire import Question, Specialty

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _SeedQuestion:
    text: str
    response_type: str
    options: Optional[List[str]] = None
    help_text: Optional[str] = None
    is_required_default: bool = False
    show_in_history_default: bool = True


@dataclass(frozen=True)
class _SeedSpecialty:
    slug: str
    name: str
    description: str
    icon: str
    questions: List[_SeedQuestion]


# Preguntas globales (transversales a cualquier especialidad)
_GLOBAL_QUESTIONS: List[_SeedQuestion] = [
    _SeedQuestion(
        text="¿Fumas actualmente?",
        response_type="yes_no",
        help_text="Si fumas de manera ocasional también marca Sí.",
    ),
    _SeedQuestion(
        text="¿Consumes bebidas alcohólicas?",
        response_type="single_choice",
        options=["Nunca", "Ocasional", "Frecuente", "Diario"],
    ),
    _SeedQuestion(
        text="¿Realizas actividad física regularmente?",
        response_type="single_choice",
        options=["Nunca", "1-2 veces/semana", "3-4 veces/semana", "5+ veces/semana"],
    ),
    _SeedQuestion(
        text="¿Tienes alergias conocidas?",
        response_type="multi_choice",
        options=["Medicamentos", "Alimentos", "Polen / ambiente", "Látex", "Otra"],
        show_in_history_default=True,
    ),
    _SeedQuestion(
        text="¿Tomas algún medicamento de forma regular?",
        response_type="long_text",
        help_text="Incluye dosis y frecuencia si es posible.",
    ),
    _SeedQuestion(
        text="¿Algún antecedente quirúrgico importante?",
        response_type="long_text",
    ),
    _SeedQuestion(
        text="Peso actual (kg)",
        response_type="numeric",
    ),
    _SeedQuestion(
        text="Estatura (cm)",
        response_type="numeric",
    ),
]


_SPECIALTIES: List[_SeedSpecialty] = [
    _SeedSpecialty(
        slug="medicina-general",
        name="Medicina general",
        description="Preguntas base de atención primaria.",
        icon="stethoscope",
        questions=[
            _SeedQuestion(
                text="¿Cuál es el motivo principal de la consulta?",
                response_type="long_text",
                is_required_default=True,
            ),
            _SeedQuestion(
                text="¿Desde cuándo presenta los síntomas?",
                response_type="short_text",
            ),
            _SeedQuestion(
                text="¿Ha tenido fiebre en los últimos 7 días?",
                response_type="yes_no",
            ),
            _SeedQuestion(
                text="¿Cómo calificaría su dolor (0 = nada, 10 = máximo)?",
                response_type="numeric",
            ),
        ],
    ),
    _SeedSpecialty(
        slug="cardiologia",
        name="Cardiología",
        description="Preguntas orientadas a salud cardiovascular.",
        icon="favorite",
        questions=[
            _SeedQuestion(
                text="¿Ha tenido dolor u opresión en el pecho?",
                response_type="yes_no",
                is_required_default=True,
            ),
            _SeedQuestion(
                text="¿Presenta palpitaciones?",
                response_type="yes_no",
            ),
            _SeedQuestion(
                text="¿Antecedentes familiares de infarto o enfermedad cardíaca?",
                response_type="yes_no",
            ),
            _SeedQuestion(
                text="Presión arterial reciente (mmHg)",
                response_type="short_text",
                help_text="Ej. 120/80",
            ),
        ],
    ),
    _SeedSpecialty(
        slug="neumologia",
        name="Neumología",
        description="Enfocada a sistema respiratorio.",
        icon="air",
        questions=[
            _SeedQuestion(
                text="¿Presenta tos actualmente?",
                response_type="single_choice",
                options=["No", "Seca", "Con flema"],
            ),
            _SeedQuestion(
                text="¿Dificultad para respirar en reposo o al esfuerzo?",
                response_type="single_choice",
                options=["No", "Esfuerzo", "Reposo"],
            ),
            _SeedQuestion(
                text="¿Exposición a humo, químicos o polvo?",
                response_type="yes_no",
            ),
        ],
    ),
    _SeedSpecialty(
        slug="ginecologia",
        name="Ginecología",
        description="Salud reproductiva y ciclo menstrual.",
        icon="female",
        questions=[
            _SeedQuestion(
                text="Fecha de la última menstruación",
                response_type="short_text",
            ),
            _SeedQuestion(
                text="¿Ciclo regular?",
                response_type="yes_no",
            ),
            _SeedQuestion(
                text="Número de embarazos previos",
                response_type="numeric",
            ),
            _SeedQuestion(
                text="¿Usa algún método anticonceptivo?",
                response_type="single_choice",
                options=["Ninguno", "Hormonal oral", "DIU", "Barrera", "Otro"],
            ),
        ],
    ),
    _SeedSpecialty(
        slug="endocrinologia",
        name="Endocrinología",
        description="Metabolismo, tiroides y diabetes.",
        icon="monitor_heart",
        questions=[
            _SeedQuestion(
                text="¿Antecedentes de diabetes en la familia?",
                response_type="yes_no",
                is_required_default=True,
            ),
            _SeedQuestion(
                text="Último valor de glucosa en sangre (mg/dL)",
                response_type="numeric",
            ),
            _SeedQuestion(
                text="¿Ha notado cambios súbitos de peso?",
                response_type="single_choice",
                options=["No", "Aumento", "Pérdida"],
            ),
            _SeedQuestion(
                text="¿Toma medicamento para tiroides?",
                response_type="yes_no",
            ),
            _SeedQuestion(
                text="Síntomas actuales",
                response_type="multi_choice",
                options=[
                    "Fatiga",
                    "Sed excesiva",
                    "Micción frecuente",
                    "Temblores",
                    "Cambios de ánimo",
                ],
            ),
        ],
    ),
    _SeedSpecialty(
        slug="neurologia",
        name="Neurología",
        description="Sistema nervioso central y periférico.",
        icon="psychology",
        questions=[
            _SeedQuestion(
                text="¿Ha sufrido dolores de cabeza frecuentes?",
                response_type="yes_no",
            ),
            _SeedQuestion(
                text="¿Ha presentado mareos o desmayos?",
                response_type="yes_no",
            ),
            _SeedQuestion(
                text="¿Adormecimiento u hormigueo en alguna parte del cuerpo?",
                response_type="long_text",
            ),
        ],
    ),
    _SeedSpecialty(
        slug="oftalmologia",
        name="Oftalmología",
        description="Salud visual y ocular.",
        icon="visibility",
        questions=[
            _SeedQuestion(
                text="¿Usa lentes de contacto o armazón?",
                response_type="single_choice",
                options=["No", "Armazón", "Contacto", "Ambos"],
            ),
            _SeedQuestion(
                text="¿Ha notado visión borrosa recientemente?",
                response_type="yes_no",
            ),
            _SeedQuestion(
                text="¿Antecedentes de glaucoma o catarata en la familia?",
                response_type="yes_no",
            ),
        ],
    ),
]


def seed_questionnaire(db: Session) -> None:
    """Siembra especialidades + preguntas del sistema si está vacío."""

    try:
        has_specialties = db.query(Specialty.id).first() is not None
        has_questions = db.query(Question.id).first() is not None
    except Exception as exc:  # tabla puede no existir aún
        logger.debug("Seed cuestionarios: tablas no disponibles aún (%s)", exc)
        return

    if has_specialties and has_questions:
        return

    try:
        specialty_by_slug: dict[str, Specialty] = {}
        if not has_specialties:
            for idx, spec in enumerate(_SPECIALTIES):
                row = Specialty(
                    slug=spec.slug,
                    name=spec.name,
                    description=spec.description,
                    icon=spec.icon,
                    sort_order=idx,
                    is_system=True,
                )
                db.add(row)
                specialty_by_slug[spec.slug] = row
            db.flush()
        else:
            for row in db.query(Specialty).all():
                specialty_by_slug[row.slug] = row

        if not has_questions:
            for idx, q in enumerate(_GLOBAL_QUESTIONS):
                db.add(
                    Question(
                        specialty_id=None,
                        owner_user_id=None,
                        origin="system",
                        text=q.text,
                        response_type=q.response_type,
                        options=q.options,
                        help_text=q.help_text,
                        is_required_default=q.is_required_default,
                        show_in_history_default=q.show_in_history_default,
                        is_active_default=True,
                        sort_order=idx,
                    )
                )

            for spec in _SPECIALTIES:
                parent = specialty_by_slug.get(spec.slug)
                if parent is None:
                    continue
                for idx, q in enumerate(spec.questions):
                    db.add(
                        Question(
                            specialty_id=parent.id,
                            owner_user_id=None,
                            origin="system",
                            text=q.text,
                            response_type=q.response_type,
                            options=q.options,
                            help_text=q.help_text,
                            is_required_default=q.is_required_default,
                            show_in_history_default=q.show_in_history_default,
                            is_active_default=True,
                            sort_order=idx,
                        )
                    )

        db.commit()
        logger.info("Seed de cuestionarios insertado (especialidades + preguntas base)")
    except Exception as exc:
        db.rollback()
        logger.exception("Error sembrando cuestionarios: %s", exc)
