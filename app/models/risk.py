"""
project-spec.md 4절(위험도 판단 로직 — 규칙 + AI 하이브리드), 9절 참고.

risk_matrix: Layer 1 결정론적 규칙 (기본 안전망)
ai_risk_logs: Layer 2 LLM 보조 판단 로그 (매트릭스가 커버 못하는 케이스)
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class RiskMatrixRule(Base):
    """
    Layer 1 규칙 한 줄 = (이벤트 유형, 트리거 조건 종류/값) -> 위험도.
    trigger_type 은 "age_group" | "tag" 중 하나 (인프라 매칭은 Phase 5).
    예: (홍수특보-경보, tag, 운전자) -> HIGH
    """

    __tablename__ = "risk_matrix"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)  # enums.EventType 값
    severity: Mapped[str | None] = mapped_column(String(20), nullable=True)  # enums.Severity 값, null이면 무관
    trigger_type: Mapped[str] = mapped_column(String(20), nullable=False)  # "age_group" | "tag"
    trigger_value: Mapped[str] = mapped_column(String(30), nullable=False)  # AgeGroup/ConsiderationTag 값
    risk_level: Mapped[str] = mapped_column(String(10), nullable=False)  # enums.RiskLevel 값


class AIRiskLog(Base):
    __tablename__ = "ai_risk_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    subscription_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(10), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)  # LLM이 왜 이렇게 판단했는지
    model: Mapped[str] = mapped_column(String(50), nullable=False)  # 예: "claude-sonnet-5"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    event: Mapped["Event"] = relationship(back_populates="ai_risk_logs")
