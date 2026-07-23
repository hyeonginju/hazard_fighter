from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import crud
from app.api.deps import get_current_user
from app.database import get_db
from app.models import User
from app.schemas.subscription import SubscriptionCreate, SubscriptionRead
from app.services.ingest import backfill_subscription

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


@router.post("", response_model=SubscriptionRead)
def create_subscription(
    payload: SubscriptionCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    subscription = crud.create_subscription(db, user, payload.person_id, payload.region_id)
    # 이미 발효 중인 특보를 놓치지 않도록, 최근 이벤트를 소급 평가해 알림 생성
    backfill_subscription(db, subscription)
    return subscription


@router.get("", response_model=list[SubscriptionRead])
def list_subscriptions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return crud.list_subscriptions(db, user)
