from fastapi import APIRouter, Depends
from pydantic import EmailStr
from sqlalchemy.orm import Session

from app import crud
from app.database import get_db
from app.schemas.device_token import DeviceTokenCreate, DeviceTokenRead

router = APIRouter(prefix="/device-tokens", tags=["device-tokens"])


class DeviceTokenCreateRequest(DeviceTokenCreate):
    user_email: EmailStr  # TODO: JWT 붙으면 제거하고 인증 사용자에서 가져옴 (Phase 2+)


@router.post("", response_model=DeviceTokenRead)
def register_device_token(payload: DeviceTokenCreateRequest, db: Session = Depends(get_db)):
    """웹 PWA 가 발급받은 FCM 토큰을 발송 대상으로 등록한다. 같은 토큰 재등록은 멱등."""
    user = crud.get_or_create_user(db, payload.user_email)
    return crud.register_device_token(db, user, payload.fcm_token, payload.platform)


@router.get("", response_model=list[DeviceTokenRead])
def list_device_tokens(user_email: EmailStr, db: Session = Depends(get_db)):
    user = crud.get_or_create_user(db, user_email)
    return crud.list_device_tokens(db, user)
