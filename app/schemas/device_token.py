import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import DevicePlatform


class DeviceTokenCreate(BaseModel):
    fcm_token: str
    platform: DevicePlatform = DevicePlatform.WEB


class DeviceTokenRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    fcm_token: str
    platform: str
    created_at: datetime
