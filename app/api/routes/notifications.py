from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models import Notification, Subscription, User
from app.schemas.event import NotificationRead

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationRead])
def list_notifications(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    stmt = (
        select(Notification)
        .join(Subscription, Notification.subscription_id == Subscription.id)
        .where(Subscription.user_id == user.id)
        .order_by(Notification.id.desc())
    )
    return list(db.scalars(stmt))
