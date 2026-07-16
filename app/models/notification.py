"""
notifications: id, subscription_id, event_id, risk_level, risk_source, message, channel, sent_at, read_at
project-spec.md 9절 참고.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subscription_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(10), nullable=False)  # enums.RiskLevel 값
    risk_source: Mapped[str] = mapped_column(String(10), nullable=False)  # enums.RiskSource 값
    message: Mapped[str] = mapped_column(Text, nullable=False)  # LLM이 생성한 자연어 알림 문구
    channel: Mapped[str] = mapped_column(String(10), nullable=False)  # enums.NotificationChannel 값
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    subscription: Mapped["Subscription"] = relationship(back_populates="notifications")
    event: Mapped["Event"] = relationship(back_populates="notifications")
