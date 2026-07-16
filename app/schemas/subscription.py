import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SubscriptionCreate(BaseModel):
    person_id: uuid.UUID
    region_id: uuid.UUID


class SubscriptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    person_id: uuid.UUID
    region_id: uuid.UUID
    created_at: datetime
