from pydantic import BaseModel
from typing import Optional
from enum import Enum

class EventType(str, Enum):
    APPOINTMENT = "appointment"   # Citas
    PRESCRIPTION = "prescription" # Recetas
    ANALYSIS = "analysis"        # Documentos/Análisis
    REGISTRATION = "registration" # Registro inicial

class TimelineEventResponse(BaseModel):
    id: str
    date: str
    time: Optional[str] = None
    title: str
    actor: str
    event_type: EventType