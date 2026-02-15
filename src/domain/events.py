from __future__ import annotations

from pydantic import BaseModel
from typing import Any, Literal, Optional


EventType = Literal[
    "SYSTEM_START",
    "SPG_SEEN",
    "SPG_PRESENT",
    "SPG_ABSENT",
    "ABSENT_ALERT_FIRED",
    "ERROR",
]


class Event(BaseModel):
    ts: float
    event_type: EventType
    outlet_id: str
    camera_id: str

    spg_id: Optional[str] = None
    name: Optional[str] = None
    similarity: Optional[float] = None

    details: dict[str, Any] = {}
