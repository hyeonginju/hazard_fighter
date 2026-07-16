from fastapi import APIRouter, Depends
from pydantic import EmailStr
from sqlalchemy.orm import Session

from app import crud
from app.database import get_db
from app.schemas.subscription import SubscriptionCreate, SubscriptionRead

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


class SubscriptionCreateRequest(SubscriptionCreate):
    user_email: EmailStr  # TODO: JWT 붙으면 제거 (Phase 2+)


@router.post("", response_model=SubscriptionRead)
def create_subscription(payload: SubscriptionCreateRequest, db: Session = Depends(get_db)):
    user = crud.get_or_create_user(db, payload.user_email)
    return crud.create_subscription(db, user, payload.person_id, payload.region_id)


@router.get("", response_model=list[SubscriptionRead])
def list_subscriptions(user_email: EmailStr, db: Session = Depends(get_db)):
    user = crud.get_or_create_user(db, user_email)
    return crud.list_subscriptions(db, user)
