from pydantic import BaseModel
from typing import Optional
from enum import Enum

class EventType(str, Enum):
    APPOINTMENT = "appointment"
    PRESCRIPTION = "prescription"
    ANALYSIS = "analysis"
    REGISTRATION = "registration"

class TimelineEventResponse(BaseModel):
    id: str
    date: str
    time: Optional[str] = None
    title: str
    actor: str
    event_type: EventType

    class Config:
        from_attributes = True