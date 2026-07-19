from fastapi import APIRouter, Depends
from pydantic import EmailStr
from sqlalchemy.orm import Session

from app import crud
from app.database import get_db
from app.schemas.subscription import SubscriptionCreate, SubscriptionRead
from app.services.ingest import backfill_subscription

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


class SubscriptionCreateRequest(SubscriptionCreate):
    user_email: EmailStr  # TODO: JWT 붙으면 제거 (Phase 2+)


@router.post("", response_model=SubscriptionRead)
def create_subscription(payload: SubscriptionCreateRequest, db: Session = Depends(get_db)):
    user = crud.get_or_create_user(db, payload.user_email)
    subscription = crud.create_subscription(db, user, payload.person_id, payload.region_id)
    # 이미 발효 중인 특보를 놓치지 않도록, 최근 이벤트를 소급 평가해 알림 생성
    backfill_subscription(db, subscription)
    return subscription


@router.get("", response_model=list[SubscriptionRead])
def list_subscriptions(user_email: EmailStr, db: Session = Depends(get_db)):
    user = crud.get_or_create_user(db, user_email)
    return crud.list_subscriptions(db, user)
