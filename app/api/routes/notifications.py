from fastapi import APIRouter, Depends
from pydantic import EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import crud
from app.database import get_db
from app.models import Notification, Subscription
from app.schemas.event import NotificationRead

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationRead])
def list_notifications(user_email: EmailStr, db: Session = Depends(get_db)):
    user = crud.get_or_create_user(db, user_email)
    stmt = (
        select(Notification)
        .join(Subscription, Notification.subscription_id == Subscription.id)
        .where(Subscription.user_id == user.id)
        .order_by(Notification.id.desc())
    )
    return list(db.scalars(stmt))
