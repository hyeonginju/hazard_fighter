import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class EventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source: str
    event_type: str
    severity: str | None = None
    region_id: uuid.UUID | None = None
    occurred_at: datetime
    raw_payload: dict[str, Any]


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    subscription_id: uuid.UUID
    event_id: uuid.UUID
    risk_level: str
    risk_source: str
    message: str
    channel: str
    sent_at: datetime | None = None
