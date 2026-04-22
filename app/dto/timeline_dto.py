from pydantic import BaseModel
from typing import Optional
from enum import Enum

class EventType(str, Enum):
    APPOINTMENT = "appointment"
    ANALYSIS = "analysis"
    COMPLETED = "completed"
    PENDING = "pending"
    REGISTRATION = "registration"

class TimelineEventResponse(BaseModel):
    id: str
    date: str
    time: Optional[str] = None
    title: str
    actor: str
    event_type: EventType
    description: Optional[str] = None

    class Config:
        from_attributes = True