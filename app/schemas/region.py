import uuid

from pydantic import BaseModel, ConfigDict


class RegionCreate(BaseModel):
    sido: str
    sigungu: str
    region_code: str | None = None


class RegionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sido: str
    sigungu: str
    region_code: str | None = None
