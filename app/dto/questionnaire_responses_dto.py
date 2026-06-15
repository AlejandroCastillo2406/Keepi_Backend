from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class PatientQuestionnaireAnswerView(BaseModel):
    question_text: str
    answer_value: Any
    answered_at: datetime
    invitation_id: str | None = None
    questionnaire_name: str | None = None
