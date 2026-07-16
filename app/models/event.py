"""
events: id, source, event_type, region_id, severity, raw_payload, occurred_at, news_refs
project-spec.md 6절(데이터 소스), 9절 참고.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.types import JsonVariant, StringArrayVariant


class Event(Base):
    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String(30), nullable=False)  # enums.EventSource 값
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)  # enums.EventType 값
    region_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("regions.id"), nullable=True)
    severity: Mapped[str | None] = mapped_column(String(20), nullable=True)  # enums.Severity 값
    raw_payload: Mapped[dict] = mapped_column(JsonVariant, nullable=False)  # 원본 API 응답 보존
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    news_refs: Mapped[list[str] | None] = mapped_column(StringArrayVariant, nullable=True)  # 참고 뉴스 링크 (보조, 6절)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    region: Mapped["Region"] = relationship(back_populates="events")
    ai_risk_logs: Mapped[list["AIRiskLog"]] = relationship(back_populates="event")
    notifications: Mapped[list["Notification"]] = relationship(back_populates="event")
