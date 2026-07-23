from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import crud
from app.api.deps import get_current_user
from app.database import get_db
from app.models import User
from app.schemas.device_token import DeviceTokenCreate, DeviceTokenRead

router = APIRouter(prefix="/device-tokens", tags=["device-tokens"])


@router.post("", response_model=DeviceTokenRead)
def register_device_token(
    payload: DeviceTokenCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """웹 PWA 가 발급받은 FCM 토큰을 발송 대상으로 등록한다. 같은 토큰 재등록은 멱등."""
    return crud.register_device_token(db, user, payload.fcm_token, payload.platform)


@router.get("", response_model=list[DeviceTokenRead])
def list_device_tokens(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return crud.list_device_tokens(db, user)
