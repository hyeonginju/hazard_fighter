import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PersonCreate(BaseModel):
    label: str
    age_group: str  # enums.AgeGroup 값
    tags: list[str] = []  # enums.ConsiderationTag 값들


class PersonRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    label: str
    age_group: str
    created_at: datetime
    tags: list[str] = []
